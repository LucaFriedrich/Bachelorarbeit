<?php
/**
 * External functions for local_competency_linker
 *
 * @package    local_competency_linker
 * @copyright  2024 Luca Friedrich
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/externallib.php');
require_once($CFG->dirroot . '/competency/lib.php');

class local_competency_linker_external extends external_api {
    
    /**
     * Describes the parameters for add_competency_to_module
     * @return external_function_parameters
     */
    public static function add_competency_to_module_parameters() {
        return new external_function_parameters(array(
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
            'competencyid' => new external_value(PARAM_INT, 'Competency ID'),
            'ruleoutcome' => new external_value(PARAM_INT, 'Rule outcome (0=None, 1=Evidence, 2=Recommend, 3=Complete)', VALUE_DEFAULT, 1)
        ));
    }
    
    /**
     * Add a competency to a course module
     * 
     * @param int $cmid Course module ID
     * @param int $competencyid Competency ID
     * @param int $ruleoutcome Rule outcome value
     * @return array Result with success status
     */
    public static function add_competency_to_module($cmid, $competencyid, $ruleoutcome = 1) {
        global $DB;
        
        // Validate parameters
        $params = self::validate_parameters(self::add_competency_to_module_parameters(), array(
            'cmid' => $cmid,
            'competencyid' => $competencyid,
            'ruleoutcome' => $ruleoutcome
        ));
        
        // Get course module to check permissions
        $cm = get_coursemodule_from_id('', $params['cmid'], 0, true, MUST_EXIST);
        $context = context_module::instance($cm->id);
        
        // Check capability
        require_capability('moodle/competency:coursecompetencymanage', $context);
        
        try {
            // Use the existing Moodle API function
            $result = \core_competency\api::add_competency_to_course_module($params['cmid'], $params['competencyid']);
            
            // Set the rule outcome if different from default
            if ($params['ruleoutcome'] !== 1 && $result) {
                $record = $DB->get_record('competency_modulecomp', array(
                    'cmid' => $params['cmid'],
                    'competencyid' => $params['competencyid']
                ), '*', MUST_EXIST);
                
                \core_competency\api::set_course_module_competency_ruleoutcome($record->id, $params['ruleoutcome']);
            }
            
            return array(
                'success' => true,
                'message' => 'Competency added to module successfully'
            );
            
        } catch (Exception $e) {
            return array(
                'success' => false,
                'message' => $e->getMessage()
            );
        }
    }
    
    /**
     * Describes the return value for add_competency_to_module
     * @return external_single_structure
     */
    public static function add_competency_to_module_returns() {
        return new external_single_structure(array(
            'success' => new external_value(PARAM_BOOL, 'Success status'),
            'message' => new external_value(PARAM_TEXT, 'Result message')
        ));
    }
    
    /**
     * Describes the parameters for remove_competency_from_module
     * @return external_function_parameters
     */
    public static function remove_competency_from_module_parameters() {
        return new external_function_parameters(array(
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
            'competencyid' => new external_value(PARAM_INT, 'Competency ID')
        ));
    }
    
    /**
     * Remove a competency from a course module
     * 
     * @param int $cmid Course module ID
     * @param int $competencyid Competency ID
     * @return array Result with success status
     */
    public static function remove_competency_from_module($cmid, $competencyid) {
        // Validate parameters
        $params = self::validate_parameters(self::remove_competency_from_module_parameters(), array(
            'cmid' => $cmid,
            'competencyid' => $competencyid
        ));
        
        // Get course module to check permissions
        $cm = get_coursemodule_from_id('', $params['cmid'], 0, true, MUST_EXIST);
        $context = context_module::instance($cm->id);
        
        // Check capability
        require_capability('moodle/competency:coursecompetencymanage', $context);
        
        try {
            // Use the existing Moodle API function
            $result = \core_competency\api::remove_competency_from_course_module($params['cmid'], $params['competencyid']);
            
            return array(
                'success' => $result,
                'message' => $result ? 'Competency removed from module successfully' : 'Failed to remove competency'
            );
            
        } catch (Exception $e) {
            return array(
                'success' => false,
                'message' => $e->getMessage()
            );
        }
    }
    
    /**
     * Describes the return value for remove_competency_from_module
     * @return external_single_structure
     */
    public static function remove_competency_from_module_returns() {
        return new external_single_structure(array(
            'success' => new external_value(PARAM_BOOL, 'Success status'),
            'message' => new external_value(PARAM_TEXT, 'Result message')
        ));
    }
    
    /**
     * Describes the parameters for set_module_competency_ruleoutcome
     * @return external_function_parameters
     */
    public static function set_module_competency_ruleoutcome_parameters() {
        return new external_function_parameters(array(
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
            'competencyid' => new external_value(PARAM_INT, 'Competency ID'),
            'ruleoutcome' => new external_value(PARAM_INT, 'Rule outcome (0=None, 1=Evidence, 2=Recommend, 3=Complete)')
        ));
    }
    
    /**
     * Set the rule outcome for a module competency
     * 
     * @param int $cmid Course module ID
     * @param int $competencyid Competency ID  
     * @param int $ruleoutcome Rule outcome value
     * @return array Result with success status
     */
    public static function set_module_competency_ruleoutcome($cmid, $competencyid, $ruleoutcome) {
        global $DB;
        
        // Validate parameters
        $params = self::validate_parameters(self::set_module_competency_ruleoutcome_parameters(), array(
            'cmid' => $cmid,
            'competencyid' => $competencyid,
            'ruleoutcome' => $ruleoutcome
        ));
        
        // Get course module to check permissions
        $cm = get_coursemodule_from_id('', $params['cmid'], 0, true, MUST_EXIST);
        $context = context_module::instance($cm->id);
        
        // Check capability
        require_capability('moodle/competency:coursecompetencymanage', $context);
        
        try {
            // Get the module competency record
            $record = $DB->get_record('competency_modulecomp', array(
                'cmid' => $params['cmid'],
                'competencyid' => $params['competencyid']
            ), '*', MUST_EXIST);
            
            // Use the existing Moodle API function
            $result = \core_competency\api::set_course_module_competency_ruleoutcome($record->id, $params['ruleoutcome']);
            
            return array(
                'success' => $result,
                'message' => 'Rule outcome updated successfully'
            );
            
        } catch (Exception $e) {
            return array(
                'success' => false,
                'message' => $e->getMessage()
            );
        }
    }
    
    /**
     * Describes the return value for set_module_competency_ruleoutcome
     * @return external_single_structure
     */
    public static function set_module_competency_ruleoutcome_returns() {
        return new external_single_structure(array(
            'success' => new external_value(PARAM_BOOL, 'Success status'),
            'message' => new external_value(PARAM_TEXT, 'Result message')
        ));
    }
}