# Moodle Integration Module

from .client import MoodleClient
from .course_downloader import CourseDownloader
# from .competency_uploader import CompetencyUploader  # TODO: Implement later

__all__ = ['MoodleClient', 'CourseDownloader']