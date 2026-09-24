import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from backend.api.app.services.analysis_input_storage import AnalysisInputStorage
from backend.api.app.services.analysis_jobs import AnalysisJobService
from backend.api.app.services.analysis_processor import AnalysisProcessor


logger = logging.getLogger(__name__)

_SAFE_FAILURE_CODE = "analysis_failed"
_SAFE_FAILURE_MESSAGE = "Analysis could not be completed."


class AnalysisJobExecutor:
    def submit(self, job_id: str) -> None:
        raise NotImplementedError


class InProcessAnalysisJobExecutor(AnalysisJobExecutor):
    def __init__(
        self,
        service: AnalysisJobService,
        input_storage: AnalysisInputStorage,
        processor: AnalysisProcessor,
        max_workers: int = 1,
    ) -> None:
        self._service = service
        self._input_storage = input_storage
        self._processor = processor
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="chordsync-analysis",
        )
        self._futures: set[Future[bool]] = set()
        self._futures_lock = Lock()

    def submit(self, job_id: str) -> None:
        future = self._pool.submit(self.run, job_id)
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(self._discard_future)

    def run(self, job_id: str) -> bool:
        if not self._service.mark_processing(job_id):
            return False

        logger.info("[job %s] processing started", job_id)
        try:
            input_path = self._input_storage.get_path(job_id)
            if input_path is None:
                raise FileNotFoundError("Stored analysis input is unavailable")
            result = self._processor.process(input_path)
            self._service.complete(job_id, result)
        except Exception:
            logger.exception("[job %s] processing failed", job_id)
            self._service.fail(
                job_id,
                code=_SAFE_FAILURE_CODE,
                message=_SAFE_FAILURE_MESSAGE,
            )
        else:
            logger.info("[job %s] completed", job_id)
        return True

    def drain(self) -> None:
        while True:
            with self._futures_lock:
                futures = tuple(self._futures)
            if not futures:
                return
            for future in futures:
                future.result()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)

    def _discard_future(self, future: Future[bool]) -> None:
        with self._futures_lock:
            self._futures.discard(future)
