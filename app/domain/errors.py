class JiraLiteError(Exception):
    """Root of the typed error hierarchy. All domain errors inherit from this."""
    code: str = "INTERNAL_ERROR"
    http_status: int = 500


class NotFoundError(JiraLiteError):
    code = "NOT_FOUND"
    http_status = 404


class ConflictError(JiraLiteError):
    code = "CONFLICT"
    http_status = 409


class WorkflowError(JiraLiteError):
    code = "WORKFLOW_VIOLATION"
    http_status = 422


class ForbiddenError(JiraLiteError):
    code = "FORBIDDEN"
    http_status = 403


class ValidationError(JiraLiteError):
    code = "VALIDATION_ERROR"
    http_status = 400
