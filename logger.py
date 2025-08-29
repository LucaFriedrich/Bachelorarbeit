# logger.py
import logging
import os

def get_logger(name: str = None) -> logging.Logger:
    logger = logging.getLogger(name or "default")

    # WICHTIG: Verhindere doppelte Handler
    if not logger.handlers:
        log_level_str = os.getenv("LOG_LEVEL", "ERROR").upper()
        log_level = getattr(logging, log_level_str, logging.ERROR)

        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.setLevel(log_level)
        
        # WICHTIG: Propagate auf False setzen um doppelte Ausgaben zu verhindern
        # wenn ein anderes Script logging.basicConfig() nutzt
        logger.propagate = False
    else:
        # Aktualisiere Log-Level bei bereits existierenden Loggern
        log_level_str = os.getenv("LOG_LEVEL", "ERROR").upper()
        log_level = getattr(logging, log_level_str, logging.ERROR)
        logger.setLevel(log_level)
        # Aktualisiere auch alle Handler
        for handler in logger.handlers:
            handler.setLevel(log_level)

    return logger

def update_all_loggers():
    """
    Aktualisiert das Log-Level aller existierenden Logger.
    Sollte nach Änderung von LOG_LEVEL aufgerufen werden.
    """
    log_level_str = os.getenv("LOG_LEVEL", "ERROR").upper()
    log_level = getattr(logging, log_level_str, logging.ERROR)
    
    # Aktualisiere alle existierenden Logger
    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        for handler in logger.handlers:
            handler.setLevel(log_level)