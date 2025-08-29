"""
Moodle REST API Client - Low-level wrapper
Keeps it simple and focused on API communication only
"""
import requests
from typing import Dict, Any, Optional
from logger import get_logger

logger = get_logger(__name__)


class MoodleClient:
    """
    Low-level Moodle REST API client.
    
    Handles authentication and basic API calls.
    Does NOT implement business logic - that's for other modules.
    """
    
    def __init__(self, url: str, token: str):
        """
        Initialize Moodle client.
        
        Args:
            url: Moodle site URL (e.g. 'https://moodle.example.com')
            token: Web service token
        """
        self.url = url.rstrip('/')
        self.token = token
        self.rest_url = f"{self.url}/webservice/rest/server.php"
        
    def _flatten_params(self, params: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
        """
        Flatten nested dicts/lists to Moodle's expected format.
        
        Moodle expects arrays as: param[index][key]=value
        And nested objects as: param[key]=value
        """
        flattened = {}
        
        for key, value in params.items():
            full_key = f"{prefix}[{key}]" if prefix else key
            
            if isinstance(value, dict):
                # Nested dict - recursively flatten
                flattened.update(self._flatten_params(value, full_key))
            elif isinstance(value, list):
                # Array - use index notation
                if len(value) == 0:
                    # Empty array Moodle needs to know it's an array even if empty
                    # Use special notation for empty arrays
                    flattened[f"{full_key}[0]"] = ''
                else:
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            flattened.update(self._flatten_params(item, f"{full_key}[{i}]"))
                        else:
                            flattened[f"{full_key}[{i}]"] = item
            else:
                # Simple value
                flattened[full_key] = value
                
        return flattened
    
    def call_function(self, function_name: str, **params) -> Dict[str, Any]:
        """
        Call a Moodle web service function.
        
        Args:
            function_name: Moodle function name (e.g. 'core_course_get_courses')
            **params: Function parameters
            
        Returns:
            API response as dict
            
        Raises:
            requests.HTTPError: On API errors
        """
        # Flatten nested parameters for Moodle's expected format
        flattened_params = self._flatten_params(params)
        
        data = {
            'wstoken': self.token,
            'wsfunction': function_name,
            'moodlewsrestformat': 'json',
            **flattened_params
        }
        
        logger.debug(f"Calling Moodle function: {function_name}")
        
        response = requests.post(self.rest_url, data=data)
        response.raise_for_status()
        
        result = response.json()
        
        # Check for Moodle errors
        if isinstance(result, dict) and 'exception' in result:
            raise Exception(f"Moodle error: {result['message']}")
            
        return result
    
    def upload_file(self, file_path: str, component: str = 'user', 
                   filearea: str = 'draft', itemid: int = 0) -> str:
        """
        Upload a file to Moodle.
        
        Args:
            file_path: Path to file
            component: Moodle component 
            filearea: File area
            itemid: Item ID
            
        Returns:
            File info from Moodle
        """
        # TODO: Implement file upload
        raise NotImplementedError("File upload not yet implemented")