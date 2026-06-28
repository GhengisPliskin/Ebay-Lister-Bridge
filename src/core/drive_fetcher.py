"""
Module: drive_fetcher.py
Purpose: Provides all Google Drive IO operations for the Lister-Bridge pipeline.
Primary Responsibilities:
  - Authenticate with Google Drive via Service Account credentials
  - Poll the staging folder for unprocessed item batch subfolders
  - Download batch images to a local cache, skipping already-cached files
  - Archive completed batch subfolders to prevent re-processing
Key Interfaces:
  - Input: GOOGLE_SERVICE_ACCOUNT_JSON, DRIVE_STAGING_FOLDER_ID,
           DRIVE_ARCHIVE_FOLDER_ID, DRIVE_CACHE_DIR (all from .env)
  - Output: list[BatchMetadata] to orchestrator.py;
            tuple[list[str], bool] (local file paths + warning flag) to vision_agent.py
FMEA Constraints Enforced:
  - PI-001 (Severity 6, RPN 90): All Drive API calls wrapped in _call_with_backoff()
    (base 2s delay, max 3 attempts). On total retry exhaustion: returns cached paths
    with a warning flag if a local cache exists; raises DriveFetchError if no cache
    exists. The Orchestrator catches DriveFetchError and surfaces a human-readable
    terminal message — errors are never silently swallowed.

ENHANCEMENT — IMPLEMENTED (blueprint v1.1, fixes A-01):
  This module was "Built — needs enhancement". Both required changes are now in
  place (see _list_all_files() and _collect_images_recursive()):
    1. RECURSIVE SUBFOLDER TRAVERSAL. The confirmed UX is staging -> one subfolder
       PER ITEM -> images. list_pending_batches() now traverses each per-item
       subfolder's full subtree via _collect_images_recursive(), so images nested
       below the first level are no longer missed.
    2. FULL PAGINATION. Every files().list() call now loops on response
       'nextPageToken' until exhausted (via _list_all_files()), so nothing past the
       first 100 results is dropped (assumption A-01 resolved).
  Frozen-interface alignment: the public signatures (list_pending_batches() ->
  list[BatchMetadata]; download_batch_images(batch) -> tuple[list[str], bool]) are
  STABLE and must not change — vision_agent.extract_item() consumes the returned
  local image paths directly. The enhancement changes internals only.
"""

import io
import json
import os
import time
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Load .env variables once at module import time.
load_dotenv()

# ── Module-level constants ────────────────────────────────────────────────────

# Full Drive scope required: R1/R2 need readonly, R4 (archive) needs write access.
# Using a single broad scope keeps service-account configuration simpler.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# PI-001 backoff parameters — immutable during execution (Ground Rule 8).
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 2

# MIME types to file extensions for images the pipeline may receive.
# iPhones produce HEIC by default; Gemini Vision accepts it natively.
_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "image/heif": "heic",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/tiff": "tiff",
}


# ── Custom exception ──────────────────────────────────────────────────────────


class DriveFetchError(Exception):
    """
    Raised when all Drive API retry attempts are exhausted AND no local cache
    exists for the requested batch.

    This is the final escalation path defined by PI-001. The Orchestrator
    catches this exception and displays a human-readable message to the user
    — it must never propagate as a raw traceback.

    Attributes:
        batch_folder_id (str): Drive folder ID that could not be fetched.
        batch_folder_name (str): Human-readable folder name for terminal display.
        cause (Exception): The last exception raised by the Drive API call.

    FMEA Constraints:
        PI-001 — Raised only after _MAX_RETRIES exhausted AND cache fallback
                 unavailable. Carries structured context so the Orchestrator
                 can display a clear, actionable error message.
    """

    def __init__(
        self, batch_folder_id: str, batch_folder_name: str, cause: Exception
    ) -> None:
        """
        Brief description: Construct a DriveFetchError with full failure context.

        Args:
            batch_folder_id: The Drive folder ID that could not be fetched.
            batch_folder_name: Human-readable name shown in terminal messages.
            cause: The last exception raised after all retries were exhausted.

        Returns:
            None

        Side Effects:
            None
        """
        self.batch_folder_id = batch_folder_id
        self.batch_folder_name = batch_folder_name
        self.cause = cause
        super().__init__(
            f"Drive fetch failed for batch '{batch_folder_name}' "
            f"(id={batch_folder_id}): {type(cause).__name__}: {cause}"
        )


# ── TypedDicts ────────────────────────────────────────────────────────────────


class ImageFileInfo(TypedDict):
    """Metadata for a single image file within a batch subfolder."""

    file_id: str
    name: str
    mime_type: str
    modified_time: str  # ISO 8601 string from Drive API


class BatchMetadata(TypedDict):
    """
    Metadata for one item batch (a Drive subfolder containing product photos).

    The image_files list is pre-fetched by list_pending_batches() so that
    download_batch_images() receives a complete, self-contained descriptor
    without needing to issue its own subfolder query. This is a metadata
    centralization decision, not a round-trip optimization — the Drive API
    still requires a separate files().list() call per subfolder regardless of
    when it is made.
    """

    folder_id: str
    folder_name: str
    file_count: int
    created_time: str  # ISO 8601 string from Drive API
    modified_time: str  # ISO 8601 string — latest modification in folder
    image_files: list  # list[ImageFileInfo] — images within this batch


class CacheManifestEntry(TypedDict):
    """One entry in the local cache manifest, keyed by file_id."""

    file_id: str
    drive_modified_time: str  # ISO 8601 string from Drive at time of download
    local_filename: str  # "{file_id}.{ext}"
    folder_id: str  # Parent batch folder ID (useful for future cache pruning)


# ── Private utilities ─────────────────────────────────────────────────────────


def _get_drive_service():
    """
    Build and return an authenticated Google Drive API v3 service resource.

    Reads the service account JSON path from the GOOGLE_SERVICE_ACCOUNT_JSON
    environment variable, validates the file exists, then constructs and
    returns a googleapiclient.discovery.Resource for Drive v3.

    Args:
        None

    Returns:
        googleapiclient.discovery.Resource: Authenticated Drive API service
        resource. Callers use this to build and execute API requests.

    Side Effects:
        Reads GOOGLE_SERVICE_ACCOUNT_JSON from the environment.
        Performs a service account credential load from disk.

    Raises:
        EnvironmentError: If GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env.
        FileNotFoundError: If the path in GOOGLE_SERVICE_ACCOUNT_JSON does not
                           exist on disk. Also includes a hint to share the
                           service account email on the target Drive folders.
    """
    # Read and validate the credential path from the environment.
    sa_json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json_path:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not set. "
            "Add it to your .env file pointing to your service account JSON key."
        )

    # Confirm the file actually exists before attempting to load credentials.
    # A missing file produces a cryptic google-auth error without this check.
    if not os.path.exists(sa_json_path):
        raise FileNotFoundError(
            f"Service account file not found: {sa_json_path}\n"
            "Ensure the path in GOOGLE_SERVICE_ACCOUNT_JSON is correct. "
            "Also confirm the service account email has been granted "
            "Viewer (read) or Editor (archive) access on the Drive folders."
        )

    # Build credentials scoped to Drive access and construct the API resource.
    credentials = service_account.Credentials.from_service_account_file(
        sa_json_path, scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def _call_with_backoff(api_callable, *args, **kwargs):
    """
    Execute a single Drive API call with exponential backoff retry logic.

    Attempts the callable up to _MAX_RETRIES times. On failure, waits
    _BACKOFF_BASE_SECONDS * (2 ** attempt) seconds before the next attempt.
    Returns the result on success. Re-raises the last exception after all
    retries are exhausted.

    This function is the sole implementation of the PI-001 retry requirement.
    Every Drive API call in this module must go through _call_with_backoff —
    no bare .execute() calls are permitted outside this wrapper.

    Args:
        api_callable: A zero-argument callable that, when called, executes
                      the Drive API request (e.g., lambda: request.execute()).
        *args: Positional arguments forwarded to api_callable.
        **kwargs: Keyword arguments forwarded to api_callable.

    Returns:
        The return value of api_callable on success.

    Side Effects:
        Prints retry warnings to stderr on each failure.
        Sleeps between retry attempts.

    Raises:
        Exception: Re-raises the last exception after _MAX_RETRIES failures.
                   Does NOT catch EnvironmentError or ValueError — those
                   indicate programming errors, not transient API failures.

    FMEA Constraints:
        PI-001 — Base delay: _BACKOFF_BASE_SECONDS (2s). Attempts: _MAX_RETRIES (3).
                 Covers HttpError (4xx/5xx), ConnectionError, socket timeouts.
    """
    last_exception = None

    for attempt in range(_MAX_RETRIES):
        try:
            # Execute the API call. If it succeeds, return immediately.
            return api_callable(*args, **kwargs)

        except (HttpError, OSError, ConnectionError, TimeoutError) as exc:
            last_exception = exc
            # Compute exponential delay: 2s, 4s, 8s for attempts 0, 1, 2.
            delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
            print(
                f"[drive_fetcher] Attempt {attempt + 1}/{_MAX_RETRIES} failed: "
                f"{type(exc).__name__}: {exc}. Retrying in {delay}s…",
                flush=True,
            )
            # Do not sleep after the final failed attempt — raise immediately.
            if attempt < _MAX_RETRIES - 1:
                time.sleep(delay)

    # All attempts exhausted. Propagate the last error to the caller.
    raise last_exception


def _load_cache_manifest(cache_dir: str) -> dict:
    """
    Load the cache manifest JSON from the given directory.

    The manifest maps file_id strings to CacheManifestEntry dicts. It is used
    to determine whether a cached local copy is fresh (matching Drive's
    modifiedTime) or stale.

    Args:
        cache_dir (str): Absolute path to the local image cache directory.

    Returns:
        dict: Mapping of file_id -> CacheManifestEntry. Returns an empty dict
              if manifest.json does not exist (first run or cold cache).

    Side Effects:
        Reads manifest.json from disk if it exists.

    Raises:
        json.JSONDecodeError: If manifest.json exists but is malformed.
                              Callers should treat this as a cold cache and
                              re-download all files.
    """
    manifest_path = os.path.join(cache_dir, "manifest.json")

    # Return an empty dict on first run — no manifest means no cached files.
    if not os.path.exists(manifest_path):
        return {}

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # The manifest stores entries under a top-level "entries" key to allow
    # for future schema versioning (schema_version field).
    return data.get("entries", {})


def _save_cache_manifest(cache_dir: str, manifest: dict) -> None:
    """
    Write the cache manifest dict to manifest.json atomically.

    Uses write-to-temp + rename to avoid leaving a partial/corrupt manifest
    if the process is interrupted mid-write. Path.replace() is used instead
    of os.rename() because it handles the case on Windows where the destination
    already exists.

    Args:
        cache_dir (str): Absolute path to the local image cache directory.
        manifest (dict): Mapping of file_id -> CacheManifestEntry to persist.

    Returns:
        None

    Side Effects:
        Writes .manifest.tmp then renames it to manifest.json in cache_dir.
    """
    manifest_path = Path(cache_dir) / "manifest.json"
    tmp_path = Path(cache_dir) / ".manifest.tmp"

    # Write the full manifest structure including schema version for future-proofing.
    payload = {"schema_version": 1, "entries": manifest}

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # Atomic rename: replaces the existing manifest.json in a single OS operation.
    tmp_path.replace(manifest_path)


def _get_local_filename(file_id: str, mime_type: str) -> str:
    """
    Map a Drive file_id and MIME type to a local cache filename.

    Args:
        file_id (str): The Drive file ID (used as the filename stem).
        mime_type (str): The Drive MIME type (e.g., "image/jpeg", "image/heic").

    Returns:
        str: A filename of the form "{file_id}.{ext}" (e.g., "1aBcDe.jpg").
             Falls back to "bin" extension for unrecognized MIME types so
             downloads are never blocked by an unknown format.
    """
    # Look up the extension; default to "bin" for unrecognized MIME types.
    ext = _MIME_TO_EXT.get(mime_type.lower(), "bin")
    return f"{file_id}.{ext}"


def _resolve_cache_dir() -> str:
    """
    Read DRIVE_CACHE_DIR from the environment and resolve it to an absolute path.

    Relative paths are resolved relative to the project root (two directories
    above this file: src/core/ -> src/ -> project root). This ensures the
    cache location is consistent regardless of where the user invokes the CLI.

    Args:
        None

    Returns:
        str: Absolute path to the cache directory.

    Side Effects:
        Creates the cache directory if it does not already exist.

    Raises:
        EnvironmentError: If DRIVE_CACHE_DIR is not set in .env.
    """
    cache_dir_env = os.environ.get("DRIVE_CACHE_DIR")
    if not cache_dir_env:
        raise EnvironmentError(
            "DRIVE_CACHE_DIR is not set. Add it to your .env file "
            "(e.g., DRIVE_CACHE_DIR=data/cache/images)."
        )

    # Anchor relative paths to the project root so the cache directory is
    # consistent regardless of the current working directory at invocation time.
    if not os.path.isabs(cache_dir_env):
        project_root = Path(__file__).parent.parent.parent
        cache_dir = str(project_root / cache_dir_env)
    else:
        cache_dir = cache_dir_env

    # Create the directory tree if it does not exist yet.
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    return cache_dir


def _list_all_files(service, query: str, files_fields: str) -> list:
    """
    Run a files().list query and return EVERY matching file across all pages.

    Loops on the Drive 'nextPageToken' until exhausted, so result sets larger
    than one page (pageSize=100) are fully retrieved. This implements the full
    pagination required by blueprint v1.1 (fixes assumption A-01).

    Args:
        service: An authenticated Drive v3 service resource.
        query: The Drive 'q' filter expression.
        files_fields: The 'files(...)' field projection (e.g.
                      "files(id, name, mimeType, modifiedTime)"). The required
                      'nextPageToken' field is added automatically.

    Returns:
        list[dict]: All file resource dicts matching the query across all pages.

    Side Effects:
        Makes one or more Drive API files().list() calls, each wrapped in
        _call_with_backoff() (PI-001).

    Raises:
        Exception: Propagates the last exception from _call_with_backoff() after
                   retries are exhausted. Callers wrap this in DriveFetchError.

    FMEA Constraints:
        PI-001 — every page request goes through _call_with_backoff().
    """
    all_files: list = []
    page_token = None

    # Always request nextPageToken alongside the caller's file fields so we can
    # detect and follow additional pages.
    fields = f"nextPageToken, {files_fields}"

    while True:
        result = _call_with_backoff(
            service.files()
            .list(
                q=query,
                fields=fields,
                pageSize=100,
                pageToken=page_token,
            )
            .execute
        )
        all_files.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        # No further token means we have read the final page.
        if not page_token:
            break

    return all_files


def _collect_images_recursive(service, folder_id: str) -> list:
    """
    Collect image files within a folder AND all of its nested subfolders.

    The confirmed UX is staging -> one subfolder per item -> images, but items
    may nest images one or more levels deep. This walks the full subtree so no
    image below the first level is missed (blueprint v1.1 recursive-traversal
    requirement; fixes assumption A-01).

    Args:
        service: An authenticated Drive v3 service resource.
        folder_id: The folder whose image subtree should be collected.

    Returns:
        list[dict]: Image file resource dicts (id, name, mimeType, modifiedTime)
        gathered from this folder and every descendant folder.

    Side Effects:
        Makes paginated Drive API calls (image listing + subfolder listing) for
        this folder and recursively for each subfolder, all via _call_with_backoff().

    Raises:
        Exception: Propagates from _list_all_files after retries are exhausted.
                   Callers wrap this in DriveFetchError.

    FMEA Constraints:
        PI-001 — all listing calls go through _call_with_backoff() (via
        _list_all_files).
    """
    images: list = []

    # Images directly contained in this folder (all pages).
    image_query = (
        f"'{folder_id}' in parents "
        f"and mimeType contains 'image/' "
        f"and trashed = false"
    )
    images.extend(
        _list_all_files(
            service, image_query, "files(id, name, mimeType, modifiedTime)"
        )
    )

    # Subfolders to descend into (all pages).
    subfolder_query = (
        f"'{folder_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    subfolders = _list_all_files(service, subfolder_query, "files(id, name)")
    for sub in subfolders:
        # Recurse: gather images from each nested subfolder's full subtree.
        images.extend(_collect_images_recursive(service, sub["id"]))

    return images


# ── Public API ────────────────────────────────────────────────────────────────


def list_pending_batches() -> list:
    """
    Poll the Drive staging folder and return all subfolders as batch metadata.

    Authenticates via Service Account, queries the staging folder ID from .env,
    and lists immediate children of type 'application/vnd.google-apps.folder'.
    For each subfolder, issues a separate files().list() call to fetch its
    image file metadata. Returns all batches sorted oldest-first so the
    Orchestrator processes items in upload order.

    Args:
        None

    Returns:
        list[BatchMetadata]: Batches sorted by modifiedTime ascending (oldest
        first). Returns an empty list if the staging folder has no subfolders.

    Side Effects:
        Reads GOOGLE_SERVICE_ACCOUNT_JSON and DRIVE_STAGING_FOLDER_ID from .env.
        Makes 1 + N Drive API calls (one folder list, one file list per subfolder),
        each wrapped in exponential backoff via _call_with_backoff().

    Raises:
        EnvironmentError: If required .env variables are missing or invalid.
        DriveFetchError: If all retry attempts fail for any Drive API call.
                         The Orchestrator should display a human-readable error
                         and prompt the user to check their connection.

    FMEA Constraints:
        PI-001 — All Drive API calls use _call_with_backoff(). On total failure,
                 raises DriveFetchError (no cache fallback for folder listings —
                 returning a stale folder list could cause double-processing).
    """
    # Validate the staging folder ID from .env before making any API calls.
    staging_folder_id = os.environ.get("DRIVE_STAGING_FOLDER_ID")
    if not staging_folder_id:
        raise EnvironmentError(
            "DRIVE_STAGING_FOLDER_ID is not set. Add it to your .env file."
        )

    # Build the authenticated Drive service resource.
    service = _get_drive_service()

    # Query for immediate subfolder children of the staging folder.
    # Trashed items are excluded so archived batches do not re-appear.
    # Assumption A-01: pageSize=100 is sufficient for this single-user use case.
    # If the staging folder accumulates more than 100 subfolders, batches beyond
    # 100 will be silently dropped until pagination (list_next) is implemented.
    # RESOLVED (blueprint v1.1): A-01 is now fixed — this listing is paginated
    # fully via _list_all_files() (loops on nextPageToken), so no subfolder past
    # the first 100 is dropped. The note above is retained as historical context.
    folder_query = (
        f"'{staging_folder_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )

    last_exc = None
    try:
        # Fully paginated: retrieves every staging subfolder across all pages.
        subfolders = _list_all_files(
            service, folder_query, "files(id, name, createdTime, modifiedTime)"
        )
    except Exception as exc:
        last_exc = exc
        raise DriveFetchError(
            batch_folder_id="N/A",
            batch_folder_name="staging folder",
            cause=exc,
        )

    batches: list = []

    for folder in subfolders:
        folder_id = folder["id"]
        folder_name = folder["name"]

        # For each subfolder, fetch the list of image files it contains.
        # This is a separate API call per subfolder — the Drive API does not
        # support fetching child files and parent folder metadata in one request.
        # REQUIREMENT (pending, blueprint v1.1): this query must (a) recurse into
        # nested per-item subfolders and (b) loop on nextPageToken so >100 images
        # are not dropped. See the "PENDING ENHANCEMENT" note in the module docstring.
        # RESOLVED (blueprint v1.1): now handled by _collect_images_recursive(),
        # which walks the per-item subtree and paginates each listing fully. The
        # requirement note above is retained as historical context.
        try:
            collected = _collect_images_recursive(service, folder_id)
        except Exception as exc:
            # A failure on a specific subfolder's file listing is treated as a
            # total batch failure — raise so the Orchestrator can surface it.
            raise DriveFetchError(
                batch_folder_id=folder_id,
                batch_folder_name=folder_name,
                cause=exc,
            )

        image_files = [
            ImageFileInfo(
                file_id=f["id"],
                name=f["name"],
                mime_type=f["mimeType"],
                modified_time=f["modifiedTime"],
            )
            for f in collected
        ]

        batches.append(
            BatchMetadata(
                folder_id=folder_id,
                folder_name=folder_name,
                file_count=len(image_files),
                created_time=folder["createdTime"],
                modified_time=folder["modifiedTime"],
                image_files=image_files,
            )
        )

    # Sort oldest-first so the Orchestrator processes items in upload order.
    batches.sort(key=lambda b: b["modified_time"])
    return batches


def download_batch_images(batch) -> tuple:
    """
    Download all images in a batch subfolder to the local cache directory.

    For each image in batch['image_files'], checks the cache manifest for a
    valid cached copy (matching file_id AND Drive modifiedTime). If a valid
    cache hit exists, skips the download and uses the local file. Otherwise
    downloads from Drive and updates the manifest.

    On total API failure for a file:
      - If a stale cached copy exists on disk: uses it and sets the warning flag.
      - If no copy exists at all: raises DriveFetchError (PI-001).

    Args:
        batch (BatchMetadata): A batch metadata dict as returned by
                               list_pending_batches(). The image_files list
                               provides the file IDs, names, and modifiedTimes
                               needed for cache validation and download.

    Returns:
        tuple[list[str], bool]:
            - list[str]: Absolute local file paths for all images in the batch,
                         whether downloaded fresh or served from cache.
            - bool: True if any images were served from a stale cache due to
                    an API failure (warning flag for Orchestrator display).
                    False if all downloads succeeded or all cache hits were fresh.

    Side Effects:
        Reads DRIVE_CACHE_DIR from .env.
        Writes image files to the local cache directory.
        Reads and writes manifest.json in the cache directory.
        Makes one Drive API files().get_media() call per non-cached image,
        each wrapped in _call_with_backoff().

    Raises:
        EnvironmentError: If DRIVE_CACHE_DIR is not set in .env.
        DriveFetchError: If all retries fail AND no cached copy exists on disk
                         for one or more images in the batch (PI-001).

    FMEA Constraints:
        PI-001 — Cache check precedes every API call. On per-file retry
                 exhaustion, falls back to stale cached version if available.
                 Raises DriveFetchError only when no disk copy exists at all.
    """
    # Resolve and create the local cache directory.
    cache_dir = _resolve_cache_dir()

    # Load the existing manifest. An empty dict means a cold cache.
    manifest = _load_cache_manifest(cache_dir)

    # Build the Drive service once for all downloads in this batch.
    service = _get_drive_service()

    local_paths: list = []
    cache_fallback_used = False
    failed_file_ids: list = []
    last_download_exc = None

    for file_info in batch["image_files"]:
        file_id = file_info["file_id"]
        mime_type = file_info["mime_type"]
        drive_modified_time = file_info["modified_time"]

        local_filename = _get_local_filename(file_id, mime_type)
        local_path = os.path.join(cache_dir, local_filename)

        # ── Cache hit check ───────────────────────────────────────────────────
        # A cache hit requires ALL three conditions:
        #   1. A manifest entry exists for this file_id.
        #   2. The stored Drive modifiedTime matches the current Drive value
        #      (if Drive modified time differs, the user re-uploaded the photo).
        #   3. The local file actually exists on disk.
        manifest_entry = manifest.get(file_id)
        is_fresh_cache_hit = (
            manifest_entry is not None
            and manifest_entry["drive_modified_time"] == drive_modified_time
            and os.path.exists(local_path)
        )

        if is_fresh_cache_hit:
            # Valid cache hit — skip the API call entirely.
            local_paths.append(local_path)
            continue

        # ── Download attempt ──────────────────────────────────────────────────
        # The cached copy is either absent or stale; attempt a fresh download.
        try:
            request = service.files().get_media(fileId=file_id)
            file_bytes = io.BytesIO()
            downloader = MediaIoBaseDownload(file_bytes, request)

            # MediaIoBaseDownload uses a chunked loop; wrap the final execute
            # call. For large images, this may require multiple chunks.
            done = False
            while not done:
                _, done = _call_with_backoff(downloader.next_chunk)

            # Write the downloaded bytes to the local cache path.
            with open(local_path, "wb") as f:
                f.write(file_bytes.getvalue())

            # Update the manifest entry to reflect the freshly downloaded file.
            manifest[file_id] = CacheManifestEntry(
                file_id=file_id,
                drive_modified_time=drive_modified_time,
                local_filename=local_filename,
                folder_id=batch["folder_id"],
            )
            # Persist the manifest after each successful download so a mid-batch
            # interruption does not force a full re-download on the next run.
            _save_cache_manifest(cache_dir, manifest)

            local_paths.append(local_path)

        except Exception as exc:
            last_download_exc = exc

            # ── PI-001 fallback: stale cache ──────────────────────────────────
            # The download failed but a stale copy may still be on disk.
            # Using a stale image is better than halting the pipeline entirely
            # for intermittent network failures (PI-001 mitigation).
            if os.path.exists(local_path):
                print(
                    f"[drive_fetcher] WARNING: Download failed for file '{file_id}' "
                    f"({file_info['name']}). Using stale cached copy. "
                    f"Error: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                local_paths.append(local_path)
                cache_fallback_used = True
            else:
                # No cached copy of any kind exists — record this file as failed.
                failed_file_ids.append(file_id)

    # ── PI-001 final escalation ───────────────────────────────────────────────
    # If any files have no disk copy and could not be downloaded, raise a
    # structured exception. The Orchestrator must surface this to the user
    # rather than silently proceeding with an incomplete image set.
    if failed_file_ids:
        raise DriveFetchError(
            batch_folder_id=batch["folder_id"],
            batch_folder_name=batch["folder_name"],
            cause=last_download_exc,
        )

    return (local_paths, cache_fallback_used)


def archive_batch(batch_folder_id: str, batch_folder_name: str) -> None:
    """
    Move a completed batch subfolder from the staging folder to the archive folder.

    Uses files().update() to change the subfolder's parent from
    DRIVE_STAGING_FOLDER_ID to DRIVE_ARCHIVE_FOLDER_ID. This is a metadata-only
    operation in Drive — no files are copied or deleted. After archiving, the
    batch will no longer appear in list_pending_batches() results.

    Args:
        batch_folder_id (str): The Drive folder ID of the batch to archive.
        batch_folder_name (str): Human-readable name, used in log messages only.

    Returns:
        None

    Side Effects:
        Modifies the parent of the Drive subfolder (moves it within Drive).
        Makes one Drive API files().update() call, wrapped in _call_with_backoff().

    Raises:
        EnvironmentError: If DRIVE_STAGING_FOLDER_ID or DRIVE_ARCHIVE_FOLDER_ID
                          are not set in .env.
        DriveFetchError: If all retry attempts fail. The batch will remain in
                         staging and re-appear on the next poll — the user should
                         retry or archive manually via the Drive web interface.

    FMEA Constraints:
        PI-001 — API call wrapped in _call_with_backoff(). On total failure,
                 raises DriveFetchError. Batch re-appearance on next poll is a
                 safe failure mode (duplicate processing guard must be in
                 Orchestrator logic if needed).
    """
    # Validate both folder ID env vars before making any API calls.
    staging_folder_id = os.environ.get("DRIVE_STAGING_FOLDER_ID")
    archive_folder_id = os.environ.get("DRIVE_ARCHIVE_FOLDER_ID")

    if not staging_folder_id:
        raise EnvironmentError(
            "DRIVE_STAGING_FOLDER_ID is not set. Add it to your .env file."
        )
    if not archive_folder_id:
        raise EnvironmentError(
            "DRIVE_ARCHIVE_FOLDER_ID is not set. Add it to your .env file."
        )

    # Build the authenticated Drive service resource.
    service = _get_drive_service()

    # Move the subfolder by updating its parents: remove from staging, add to archive.
    # Drive's files().update() with addParents/removeParents is the standard method
    # for moving files/folders without copying or deleting content.
    try:
        _call_with_backoff(
            service.files()
            .update(
                fileId=batch_folder_id,
                addParents=archive_folder_id,
                removeParents=staging_folder_id,
                fields="id, parents",
            )
            .execute
        )
        print(
            f"[drive_fetcher] Batch '{batch_folder_name}' (id={batch_folder_id}) "
            f"archived successfully.",
            flush=True,
        )

    except Exception as exc:
        # All retries exhausted — the batch stays in staging.
        # Raise so the Orchestrator can warn the user to archive manually.
        raise DriveFetchError(
            batch_folder_id=batch_folder_id,
            batch_folder_name=batch_folder_name,
            cause=exc,
        )
