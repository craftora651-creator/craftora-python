"""
Craftora - Structured Logging Module
Centralized logging configuration with structured JSON output for production.
"""

import os
import sys
import json
import logging
import logging.config
import logging.handlers
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union
import traceback
from pathlib import Path

# Global flag to prevent multiple initialization
_LOGGING_INITIALIZED = False

# ==================== LAZY SETTINGS IMPORT ====================

# DÜZELTİLMİŞ:
_SETTINGS = None

def set_settings(settings_obj):
    """Manually set settings to avoid circular imports."""
    global _SETTINGS
    _SETTINGS = settings_obj

def _get_settings():
    """Get settings with fallback."""
    if _SETTINGS:
        return _SETTINGS
    
    # Only try to import if not already set
    try:
        from config.config import settings
        return settings
    except ImportError:
        class DefaultSettings:
            ENVIRONMENT = "development"
            LOG_LEVEL = "INFO"
            LOG_BASE_DIR = "logs"
        return DefaultSettings()


# ==================== CUSTOM LOG RECORD ====================

class StructuredLogRecord(logging.LogRecord):
    """Extended LogRecord with structured data support."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timestamp = datetime.now(timezone.utc).isoformat()
        
        # Lazy load settings
        try:
            settings = _get_settings()
            self.environment = settings.ENVIRONMENT
        except:
            self.environment = "development"
            
        self.service = "fastapi-backend"
        
        # Parse message if it's a dict
        if isinstance(self.msg, dict):
            self.structured_data = self.msg
            self.msg = json.dumps(self.msg)
        else:
            self.structured_data = {}


# ==================== CUSTOM FILTERS ====================

class ContextFilter(logging.Filter):
    """Add contextual information to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Add request ID if available
        if hasattr(record, 'request_id'):
            record.request_id = getattr(record, 'request_id', None)
        
        # Add user info if available
        if hasattr(record, 'user_id'):
            record.user_id = getattr(record, 'user_id', None)
        if hasattr(record, 'user_email'):
            record.user_email = getattr(record, 'user_email', None)
        
        # Add shop info if available
        if hasattr(record, 'shop_id'):
            record.shop_id = getattr(record, 'shop_id', None)
        
        # Add IP address if available
        if hasattr(record, 'client_ip'):
            record.client_ip = getattr(record, 'client_ip', None)
        
        return True


class ProductionFilter(logging.Filter):
    """Filter logs in production environment."""
    
    def __init__(self):
        super().__init__()
        self.environment = _get_settings().ENVIRONMENT
    
    def filter(self, record: logging.LogRecord) -> bool:
        # In production, hide DEBUG logs
        if self.environment == "production" and record.levelno == logging.DEBUG:
            return False
        
        # Hide sensitive data
        if hasattr(record, 'args'):
            record.args = self._sanitize_args(record.args)
        
        return True
    
    def _sanitize_args(self, args):
        """Sanitize sensitive information from log arguments."""
        if not isinstance(args, (tuple, dict)):
            return args
        
        sensitive_fields = [
            'password', 'token', 'secret', 'key', 'authorization',
            'credit_card', 'cvv', 'ssn', 'iban', 'api_key'
        ]
        
        if isinstance(args, dict):
            for field in sensitive_fields:
                if field in args:
                    args[field] = '[REDACTED]'
        elif isinstance(args, tuple):
            args = tuple(
                '[REDACTED]' if any(s in str(arg).lower() for s in sensitive_fields) 
                else arg for arg in args
            )
        
        return args


# ==================== CUSTOM FORMATTERS ====================

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(self):
        super().__init__()
        self.settings = _get_settings()
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": getattr(record, 'timestamp', datetime.now(timezone.utc).isoformat()),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "environment": getattr(record, 'environment', self.settings.ENVIRONMENT),
            "service": getattr(record, 'service', 'fastapi-backend'),
        }
        
        # Add contextual information
        context_fields = [
            'request_id', 'user_id', 'user_email', 'user_role',
            'shop_id', 'shop_name', 'client_ip', 'path', 'method',
            'status_code', 'response_time', 'database_query', 
            'external_service', 'job_id', 'correlation_id'
        ]
        
        for field in context_fields:
            value = getattr(record, field, None)
            if value is not None:
                log_data[field] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "stack_trace": traceback.format_exception(*record.exc_info)
            }
        
        # Add structured data if present
        if hasattr(record, 'structured_data') and record.structured_data:
            log_data["data"] = record.structured_data
        
        # Add performance metrics if present
        if hasattr(record, 'duration_ms'):
            log_data["duration_ms"] = record.duration_ms
        
        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter for development."""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def format(self, record: logging.LogRecord) -> str:
        # Color coding for different levels (only for console)
        if sys.stdout.isatty():  # Only colorize if terminal supports it
            colors = {
                'DEBUG': '\033[36m',      # Cyan
                'INFO': '\033[32m',       # Green
                'WARNING': '\033[33m',    # Yellow
                'ERROR': '\033[31m',      # Red
                'CRITICAL': '\033[41m',   # Red background
            }
            
            level_color = colors.get(record.levelname, '\033[0m')
            reset_color = '\033[0m'
            
            # Format the level name with color
            record.levelname = f"{level_color}{record.levelname}{reset_color}"
        
        return super().format(record)


# ==================== CUSTOM HANDLERS ====================

class RotatingJSONFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating file handler with JSON formatting."""
    
    def __init__(self, filename, **kwargs):
        # Set defaults if not provided
        kwargs.setdefault('maxBytes', 10 * 1024 * 1024)  # 10MB
        kwargs.setdefault('backupCount', 10)
        super().__init__(filename=filename, **kwargs)
        self.setFormatter(JSONFormatter())


class ErrorFileHandler(logging.handlers.RotatingFileHandler):
    """Separate handler for error logs."""
    
    def __init__(self, filename, **kwargs):
        kwargs.setdefault('maxBytes', 5 * 1024 * 1024)  # 5MB
        kwargs.setdefault('backupCount', 5)
        super().__init__(filename=filename, **kwargs)
        self.setFormatter(JSONFormatter())
        self.setLevel(logging.ERROR)


# ==================== LOGGING CONFIGURATION ====================

def get_log_dir() -> Path:
    """Get log directory based on environment."""
    settings = _get_settings()
    log_base = Path(settings.LOG_BASE_DIR) if hasattr(settings, 'LOG_BASE_DIR') else Path("logs")
    log_dir = log_base / settings.ENVIRONMENT
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging() -> None:
    """Configure logging based on environment. Safe to call multiple times."""
    global _LOGGING_INITIALIZED
    
    if _LOGGING_INITIALIZED:
        return
    
    settings = _get_settings()
    
    # Determine log level from settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Get log directory
    log_dir = get_log_dir()
    
    # 🔥 DÜZELTME: Doğrudan class referansları kullan (string path yerine)
    # Ayrıca modülün gerçek path'ini al
    current_module = __name__  # "nix.logging" veya "core.logging" olacak
    
    # Configure logging with direct class references
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context_filter": {
                "()": ContextFilter,  # 🔥 DIRECT CLASS REFERENCE
            },
            "production_filter": {
                "()": ProductionFilter,  # 🔥 DIRECT CLASS REFERENCE
            }
        },
        "formatters": {
            "json": {
                "()": JSONFormatter,  # 🔥 DIRECT CLASS REFERENCE
            },
            "console": {
                "()": ConsoleFormatter,  # 🔥 DIRECT CLASS REFERENCE
            },
            "simple": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "console",
                "stream": sys.stdout,
                "filters": ["context_filter", "production_filter"]
            },
            "file": {
                "()": RotatingJSONFileHandler,  # 🔥 DIRECT CLASS REFERENCE
                "level": log_level,
                "filename": log_dir / "app.log",
                "filters": ["context_filter", "production_filter"]
            },
            "error_file": {
                "()": ErrorFileHandler,  # 🔥 DIRECT CLASS REFERENCE
                "level": logging.ERROR,
                "filename": log_dir / "error.log",
                "filters": ["context_filter", "production_filter"]
            },
            "access_file": {
                "()": RotatingJSONFileHandler,  # 🔥 DIRECT CLASS REFERENCE
                "level": logging.INFO,
                "filename": log_dir / "access.log",
                "filters": ["context_filter", "production_filter"]
            }
        },
        "loggers": {
            "": {  # Root logger
                "level": log_level,
                "handlers": ["console", "file", "error_file"],
                "propagate": True
            },
            "app": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False
            },
            "uvicorn": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False
            },
            "uvicorn.access": {
                "level": logging.INFO,
                "handlers": ["access_file"],
                "propagate": False
            },
            "uvicorn.error": {
                "level": log_level,
                "handlers": ["console", "file", "error_file"],
                "propagate": False
            },
            "sqlalchemy.engine": {
                "level": logging.WARNING if settings.ENVIRONMENT == "production" else logging.INFO,
                "handlers": ["file"],
                "propagate": False
            },
            "sqlalchemy.pool": {
                "level": logging.WARNING,
                "handlers": ["file"],
                "propagate": False
            },
            "aiosqlite": {
                "level": logging.WARNING,
                "handlers": ["file"],
                "propagate": False
            },
            "httpx": {
                "level": logging.WARNING,
                "handlers": ["file"],
                "propagate": False
            }
        }
    }
    
    try:
        # Apply configuration
        logging.config.dictConfig(logging_config)
        
        # Set custom log record factory
        logging.setLogRecordFactory(StructuredLogRecord)
        
        # Mark as initialized
        _LOGGING_INITIALIZED = True
        
        logger = logging.getLogger(__name__)
        logger.info(f" Logging configured for {settings.ENVIRONMENT} environment (level: {log_level})")
        
    except Exception as e:
        print(f" Logging configuration failed: {e}", file=sys.stderr)
        # Fallback to basic logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        _LOGGING_INITIALIZED = True


# ==================== LOGGING UTILITIES ====================

class RequestLogger:
    """Utility for logging HTTP requests with context."""
    
    def __init__(self, logger_name: str = "app.request"):
        self.logger = logging.getLogger(logger_name)
    
    async def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        client_ip: str,
        user_agent: str,
        user_id: Optional[str] = None,
        shop_id: Optional[str] = None
    ):
        """Log incoming request."""
        extra = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "user_id": user_id,
            "shop_id": shop_id,
            "event": "request_start"
        }
        
        self.logger.info(f"Request started: {method} {path}", extra=extra)
    
    async def log_response(
        self,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        response_time_ms: float,
        user_id: Optional[str] = None,
        shop_id: Optional[str] = None
    ):
        """Log request completion."""
        extra = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "response_time": response_time_ms,
            "user_id": user_id,
            "shop_id": shop_id,
            "event": "request_complete"
        }
        
        level = logging.ERROR if status_code >= 400 else logging.INFO
        self.logger.log(
            level,
            f"Request completed: {method} {path} -> {status_code} ({response_time_ms:.2f}ms)",
            extra=extra
        )
    
    async def log_error(
        self,
        request_id: str,
        method: str,
        path: str,
        error: Exception,
        status_code: int = 500,
        user_id: Optional[str] = None
    ):
        """Log request error."""
        extra = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "user_id": user_id,
            "event": "request_error"
        }
        
        self.logger.error(
            f"Request error: {method} {path} -> {status_code}: {error}",
            extra=extra,
            exc_info=error
        )


class PerformanceLogger:
    """Utility for logging performance metrics."""
    
    def __init__(self, logger_name: str = "app.performance"):
        self.logger = logging.getLogger(logger_name)
    
    def log_database_query(
        self,
        query: str,
        duration_ms: float,
        rows_returned: Optional[int] = None,
        user_id: Optional[str] = None,
        shop_id: Optional[str] = None
    ):
        """Log database query performance."""
        extra = {
            "database_query": query[:100] + "..." if len(query) > 100 else query,
            "duration_ms": duration_ms,
            "rows_returned": rows_returned,
            "user_id": user_id,
            "shop_id": shop_id,
            "event": "database_query"
        }
        
        if duration_ms > 1000:  # Slow query
            self.logger.warning(
                f"Slow query: {duration_ms:.2f}ms",
                extra=extra
            )
        else:
            self.logger.debug(
                f"Query executed: {duration_ms:.2f}ms",
                extra=extra
            )
    
    def log_external_service_call(
        self,
        service: str,
        endpoint: str,
        duration_ms: float,
        status_code: Optional[int] = None,
        user_id: Optional[str] = None
    ):
        """Log external service call."""
        extra = {
            "external_service": service,
            "endpoint": endpoint,
            "duration_ms": duration_ms,
            "status_code": status_code,
            "user_id": user_id,
            "event": "external_service_call"
        }
        
        level = logging.ERROR if status_code and status_code >= 400 else logging.INFO
        self.logger.log(
            level,
            f"{service} call: {endpoint} -> {duration_ms:.2f}ms",
            extra=extra
        )
    
    def log_job_execution(
        self,
        job_name: str,
        duration_ms: float,
        success: bool,
        items_processed: Optional[int] = None,
        job_id: Optional[str] = None
    ):
        """Log background job execution."""
        extra = {
            "job_name": job_name,
            "duration_ms": duration_ms,
            "success": success,
            "items_processed": items_processed,
            "job_id": job_id,
            "event": "job_execution"
        }
        
        level = logging.ERROR if not success else logging.INFO
        self.logger.log(
            level,
            f"Job {job_name} {'completed' if success else 'failed'}: {duration_ms:.2f}ms",
            extra=extra
        )


class AuditLogger:
    """Utility for audit logging (security-critical events)."""
    
    def __init__(self, logger_name: str = "app.audit"):
        self.logger = logging.getLogger(logger_name)
    
    def log_user_login(
        self,
        user_id: str,
        user_email: str,
        method: str,
        ip_address: str,
        user_agent: str,
        success: bool,
        failure_reason: Optional[str] = None
    ):
        """Log user login attempt."""
        extra = {
            "user_id": user_id,
            "user_email": user_email,
            "method": method,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "success": success,
            "failure_reason": failure_reason,
            "event": "user_login"
        }
        
        level = logging.WARNING if not success else logging.INFO
        self.logger.log(
            level,
            f"User login: {user_email} via {method} - {'Success' if success else 'Failed'}",
            extra=extra
        )
    
    def log_role_change(
        self,
        target_user_id: str,
        target_user_email: str,
        changed_by_user_id: str,
        old_role: str,
        new_role: str
    ):
        """Log user role change."""
        extra = {
            "target_user_id": target_user_id,
            "target_user_email": target_user_email,
            "changed_by_user_id": changed_by_user_id,
            "old_role": old_role,
            "new_role": new_role,
            "event": "role_change"
        }
        
        self.logger.info(
            f"Role changed: {target_user_email} from {old_role} to {new_role}",
            extra=extra
        )
    
    def log_payment_event(
        self,
        payment_id: str,
        amount: float,
        currency: str,
        user_id: str,
        shop_id: str,
        event_type: str,
        status: str
    ):
        """Log payment-related events."""
        extra = {
            "payment_id": payment_id,
            "amount": amount,
            "currency": currency,
            "user_id": user_id,
            "shop_id": shop_id,
            "event_type": event_type,
            "status": status,
            "event": "payment_event"
        }
        
        self.logger.info(
            f"Payment {event_type}: {payment_id} - {amount} {currency}",
            extra=extra
        )

# AuditLogger class'ından sonra ekle:
class RateLimitLogger:
    """Rate limit logging için özel logger."""
    
    def __init__(self, logger_name: str = "app.rate_limit"):
        self.logger = logging.getLogger(logger_name)
    
    def log_rate_limit_hit(self, client_ip: str, endpoint: str, limit: int):
        extra = {
            "client_ip": client_ip,
            "endpoint": endpoint,
            "rate_limit": limit,
            "event": "rate_limit_hit"
        }
        self.logger.warning(f"Rate limit hit: {client_ip} -> {endpoint}", extra=extra)


# Don't auto-initialize - let the app call setup_logging()
# Create global logger instances (will be initialized when needed)
logger = None
request_logger = None
performance_logger = None
audit_logger = None


def get_logger() -> logging.Logger:
    """Get the main application logger."""
    global logger
    if logger is None:
        setup_logging()
        logger = logging.getLogger("app")
    return logger


def get_request_logger() -> RequestLogger:
    """Get the request logger instance."""
    global request_logger
    if request_logger is None:
        setup_logging()
        request_logger = RequestLogger()
    return request_logger


def get_performance_logger() -> PerformanceLogger:
    """Get the performance logger instance."""
    global performance_logger
    if performance_logger is None:
        setup_logging()
        performance_logger = PerformanceLogger()
    return performance_logger


def get_audit_logger() -> AuditLogger:
    """Get the audit logger instance."""
    global audit_logger
    if audit_logger is None:
        setup_logging()
        audit_logger = AuditLogger()
    return audit_logger




class RateLimitLogger:
    """Rate limit logging için özel logger."""
    
    def log_rate_limit_hit(self, client_ip: str, endpoint: str, limit: int):
        extra = {
            "client_ip": client_ip,
            "endpoint": endpoint,
            "rate_limit": limit,
            "event": "rate_limit_hit"
        }
        self.logger.warning(f"Rate limit hit: {client_ip} -> {endpoint}", extra=extra)
        

# Export
__all__ = [
    "setup_logging",
    "get_logger",
    "get_request_logger",
    "get_performance_logger",
    "get_audit_logger",
    "JSONFormatter",
    "ConsoleFormatter",
    "RequestLogger",
    "PerformanceLogger",
    "AuditLogger",
    "StructuredLogRecord",
    "ContextFilter",
    "ProductionFilter",
    "RotatingJSONFileHandler",
    "ErrorFileHandler",
]


# Ekle: Rate limit logging için
