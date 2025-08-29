"""
Moodle Course Downloader - Downloads course content for analysis
"""
import os
from logger import get_logger
from typing import List, Dict, Optional
import requests
from pathlib import Path

from .client import MoodleClient

logger = get_logger(__name__)


class CourseDownloader:
    """Downloads course content from Moodle for analysis."""
    
    def __init__(self, client: MoodleClient):
        self.client = client
    
    def get_all_courses(self) -> List[Dict]:
        """
        Holt alle verfügbaren Kurse von Moodle.
        
        Returns:
            Liste von Kurs-Dictionaries mit:
            - id: Kurs-ID
            - shortname: Kurz-Name (z.B. "tk1")
            - fullname: Voller Name
            - summary: Kursbeschreibung (optional)
        """
        logger.info("Fetching all courses from Moodle")
        courses = self.client.call_function('core_course_get_courses')
        
        # Filtere System-Kurs raus (ID 1 ist Startseite)
        filtered_courses = []
        for course in courses:
            if course['id'] != 1:  # Skip site home
                filtered_courses.append({
                    'id': course['id'],
                    'shortname': course['shortname'],
                    'fullname': course['fullname'],
                    'summary': course.get('summary', '')
                })
        
        logger.info(f"Found {len(filtered_courses)} courses")
        return filtered_courses
        
    def get_course_by_shortname(self, shortname: str) -> Optional[Dict]:
        """
        Find course by shortname.
        
        Args:
            shortname: Course shortname (e.g. 'RN2024')
            
        Returns:
            Course info dict or None if not found
        """
        # Get all courses (filtered by shortname if API supports it)
        courses = self.client.call_function(
            'core_course_get_courses_by_field',
            field='shortname',
            value=shortname
        )
        
        if courses and 'courses' in courses and len(courses['courses']) > 0:
            course = courses['courses'][0]
            logger.info(f"Found course: {course['fullname']} (ID: {course['id']})")
            return course
        
        logger.warning(f"Course with shortname '{shortname}' not found")
        return None
    
    def get_course_contents(self, course_id: int) -> List[Dict]:
        """
        Get course contents (sections, modules, files).
        
        Args:
            course_id: Moodle course ID
            
        Returns:
            List of course sections with modules
        """
        contents = self.client.call_function(
            'core_course_get_contents',
            courseid=course_id
        )
        return contents
    
    def download_course_files(self, course_id: int, target_dir: str) -> List[str]:
        """
        Download all files from a course.
        
        Args:
            course_id: Moodle course ID
            target_dir: Directory to save files
            
        Returns:
            List of downloaded file paths
        """
        downloaded_files = []
        contents = self.get_course_contents(course_id)
        
        # Create target directory
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        
        for section in contents:
            section_name = section.get('name', 'Section')
            logger.info(f"Processing section: {section_name}")
            
            for module in section.get('modules', []):
                if module['modname'] == 'resource':  # File resource
                    file_info = self._download_module_files(module, target_dir)
                    downloaded_files.extend(file_info)
                elif module['modname'] == 'folder':  # Folder with files
                    file_info = self._download_module_files(module, target_dir)
                    downloaded_files.extend(file_info)
                    
        logger.info(f"Downloaded {len(downloaded_files)} files from course")
        return downloaded_files
    
    def _download_module_files(self, module: Dict, target_dir: str) -> List[str]:
        """Download files from a module."""
        downloaded = []
        
        for content in module.get('contents', []):
            if content['type'] == 'file':
                file_url = content['fileurl']
                filename = content['filename']
                
                # Add token to URL
                if '?' in file_url:
                    file_url += f"&token={self.client.token}"
                else:
                    file_url += f"?token={self.client.token}"
                
                # Download file
                target_path = os.path.join(target_dir, filename)
                
                try:
                    logger.debug(f"Downloading: {filename}")
                    response = requests.get(file_url)
                    response.raise_for_status()
                    
                    with open(target_path, 'wb') as f:
                        f.write(response.content)
                    
                    downloaded.append(target_path)
                    logger.info(f"Downloaded: {filename}")
                    
                except Exception as e:
                    logger.error(f"Failed to download {filename}: {e}")
                    
        return downloaded
    
    def get_enrolled_users(self, course_id: int) -> List[Dict]:
        """Get list of enrolled users in course."""
        users = self.client.call_function(
            'core_enrol_get_enrolled_users',
            courseid=course_id
        )
        return users
    
    def get_course_assignments(self, course_id: int) -> List[Dict]:
        """
        Get detailed assignment information including descriptions.
        
        Args:
            course_id: Moodle course ID
            
        Returns:
            List of assignments with full details including intro/description
        """
        try:
            result = self.client.call_function(
                'mod_assign_get_assignments',
                **{'courseids[0]': course_id}
            )
            
            # Check for warnings
            if 'warnings' in result and result['warnings']:
                for warning in result['warnings']:
                    logger.warning(f"Moodle Warning: {warning.get('message', 'Unknown warning')}")
            
            if 'courses' in result and result['courses']:
                for course in result['courses']:
                    logger.info(f"Checking course ID {course.get('id')} against {course_id}")
                    if course['id'] == course_id:
                        assignments = course.get('assignments', [])
                        logger.info(f"Found {len(assignments)} assignments in course")
                        
                        # Clean up the intro text (remove HTML)
                        for assign in assignments:
                            if 'intro' in assign:
                                # Basic HTML stripping
                                import re
                                clean_intro = re.sub('<[^<]+?>', '', assign['intro'])
                                assign['intro_text'] = clean_intro.strip()
                        
                        return assignments
            
            return []
        except Exception as e:
            logger.error(f"Failed to get assignments: {e}")
            return []
    
    def get_assignment_submissions(self, assignment_id: int) -> List[Dict]:
        """
        Get submissions for an assignment.
        
        Args:
            assignment_id: The assignment ID
            
        Returns:
            List of submissions
        """
        try:
            # Moodle expects array parameters in special format: assignmentids[0]=1
            params = {
                'assignmentids[0]': assignment_id
            }
            result = self.client.call_function(
                'mod_assign_get_submissions',
                **params
            )
            
            if 'assignments' in result and len(result['assignments']) > 0:
                assignment = result['assignments'][0]
                return assignment.get('submissions', [])
            
            return []
        except Exception as e:
            logger.error(f"Failed to get submissions: {e}")
            return []
    
    def download_assignment_submissions(self, course_id: int, target_dir: str, 
                                      only_submitted: bool = True) -> Dict[str, List[str]]:
        """
        Download all assignment submissions from a course.
        
        Creates structure:
        target_dir/
        └── submissions/
            └── user_{userid}/
                └── assignment_{assignmentname}/
                    └── files...
        
        Args:
            course_id: Moodle course ID
            target_dir: Base directory to save submissions
            only_submitted: If True, only download submitted assignments (not 'new')
            
        Returns:
            Dict mapping assignment names to list of downloaded file paths
        """
        downloaded_submissions = {}
        contents = self.get_course_contents(course_id)
        
        # Create submissions directory
        submissions_dir = Path(target_dir) / "submissions"
        submissions_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Downloading assignment submissions to: {submissions_dir}")
        
        # Find all assignments
        for section in contents:
            assignment_modules = [m for m in section.get('modules', []) 
                                if m['modname'] == 'assign']
            
            for assign in assignment_modules:
                assign_name = assign.get('name', 'Unknown')
                assign_id = assign.get('instance')
                
                if not assign_id:
                    logger.warning(f"No instance ID for assignment: {assign_name}")
                    continue
                
                logger.info(f"Processing assignment: {assign_name}")
                
                # Get submissions for this assignment
                submissions = self.get_assignment_submissions(assign_id)
                
                if not submissions:
                    logger.info(f"  No submissions found for: {assign_name}")
                    continue
                
                downloaded_files = []
                
                for submission in submissions:
                    user_id = submission.get('userid')
                    status = submission.get('status', 'unknown')
                    
                    # Skip if only_submitted and status is not 'submitted'
                    if only_submitted and status != 'submitted':
                        logger.debug(f"  Skipping user {user_id} - status: {status}")
                        continue
                    
                    # Create user/assignment directory
                    safe_assign_name = "".join(c for c in assign_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    user_dir = submissions_dir / f"user_{user_id}" / f"assignment_{safe_assign_name}"
                    user_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Download files from submission
                    for plugin in submission.get('plugins', []):
                        if plugin['type'] == 'file':
                            for filearea in plugin.get('fileareas', []):
                                for file_info in filearea.get('files', []):
                                    file_url = file_info['fileurl']
                                    filename = file_info['filename']
                                    
                                    # Add token to URL
                                    if '?' in file_url:
                                        file_url += f"&token={self.client.token}"
                                    else:
                                        file_url += f"?token={self.client.token}"
                                    
                                    # Download file
                                    target_path = user_dir / filename
                                    
                                    try:
                                        logger.info(f"  Downloading submission from user {user_id}: {filename}")
                                        response = requests.get(file_url)
                                        response.raise_for_status()
                                        
                                        with open(target_path, 'wb') as f:
                                            f.write(response.content)
                                        
                                        downloaded_files.append(str(target_path))
                                        logger.info(f"   Downloaded: {target_path}")
                                        
                                    except Exception as e:
                                        logger.error(f"   Failed to download {filename}: {e}")
                
                if downloaded_files:
                    downloaded_submissions[assign_name] = downloaded_files
        
        # Summary
        total_files = sum(len(files) for files in downloaded_submissions.values())
        logger.info(f"Downloaded {total_files} submission files from {len(downloaded_submissions)} assignments")
        
        return downloaded_submissions