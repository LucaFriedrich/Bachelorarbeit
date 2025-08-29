# Moodle Plugin Installation Guide

## Plugin: local_competency_linker

This plugin exposes Moodle's existing competency-module linking functions as Web Services.

## Installation Steps:

1. **Upload the plugin:**
   ```bash
   # Copy the folder to your Moodle installation
   cp -r local_competency_linker /path/to/moodle/local/
   ```

2. **Set correct permissions:**
   ```bash
   cd /path/to/moodle/local/competency_linker
   chmod -R 755 .
   chown -R www-data:www-data .  # Or appropriate web server user
   ```

3. **Install via Moodle:**
   - Login as admin
   - Go to Site Administration → Notifications
   - Moodle will detect the new plugin and guide you through installation

4. **Enable the Web Service functions:**
   - Go to Site Administration → Plugins → Web services → External services
   - Click "Add" to create a new service
   - Name: "Competency Module Linker"
   - Short name: "competency_linker"
   - Enabled: Yes
   - Authorized users only: Yes
   
5. **Add functions to the service:**
   - Add these functions:
     - local_competency_linker_add_competency_to_module
     - local_competency_linker_remove_competency_from_module
     - local_competency_linker_set_module_competency_ruleoutcome

6. **Create or update token:**
   - Go to Site Administration → Plugins → Web services → Manage tokens
   - Create a new token for your user with the new service
   - Or add the new service to your existing token

## Testing the Plugin:

```python
from llm.moodle.client import MoodleClient

client = MoodleClient(moodle_url, token)

# Test adding a competency to a module
result = client.call_function(
    'local_competency_linker_add_competency_to_module',
    cmid=15,  # Module ID
    competencyid=10,  # Competency ID
    ruleoutcome=1  # Evidence
)
print(result)
```

## What This Plugin Does:

1. **Exposes existing Moodle core functions** that were not available via Web Service
2. **No database changes** - uses Moodle's existing tables
3. **Respects permissions** - requires moodle/competency:coursecompetencymanage capability
4. **Minimal footprint** - ~200 lines of code, 4 files

## Files Included:

- `version.php` - Plugin version information
- `db/services.php` - Web service function definitions  
- `externallib.php` - Implementation wrapping existing Moodle API
- `lang/en/local_competency_linker.php` - Language strings

## Important Notes:

- This plugin requires Moodle 3.8+ (when module competencies were introduced)
- The underlying PHP functions already exist in Moodle core
- We're just exposing them as Web Services
- No custom database tables or complex logic needed