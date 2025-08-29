<?php
/**
 * Web service definitions for local_competency_linker
 *
 * @package    local_competency_linker
 * @copyright  2025 Luca Friedrich
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$functions = array(
    'local_competency_linker_add_competency_to_module' => array(
        'classname'   => 'local_competency_linker_external',
        'methodname'  => 'add_competency_to_module',
        'classpath'   => 'local/competency_linker/externallib.php',
        'description' => 'Add a competency to a course module',
        'type'        => 'write',
        'capabilities'=> 'moodle/competency:coursecompetencymanage',
        'ajax'        => true,
        'services'    => array(MOODLE_OFFICIAL_MOBILE_SERVICE)
    ),
    
    'local_competency_linker_remove_competency_from_module' => array(
        'classname'   => 'local_competency_linker_external',
        'methodname'  => 'remove_competency_from_module',
        'classpath'   => 'local/competency_linker/externallib.php',
        'description' => 'Remove a competency from a course module',
        'type'        => 'write',
        'capabilities'=> 'moodle/competency:coursecompetencymanage',
        'ajax'        => true,
        'services'    => array(MOODLE_OFFICIAL_MOBILE_SERVICE)
    ),
    
    'local_competency_linker_set_module_competency_ruleoutcome' => array(
        'classname'   => 'local_competency_linker_external',
        'methodname'  => 'set_module_competency_ruleoutcome',
        'classpath'   => 'local/competency_linker/externallib.php',
        'description' => 'Set the rule outcome for a module competency',
        'type'        => 'write',
        'capabilities'=> 'moodle/competency:coursecompetencymanage',
        'ajax'        => true,
        'services'    => array(MOODLE_OFFICIAL_MOBILE_SERVICE)
    )
);

// Define the service
$services = array(
    'Competency Module Linker Service' => array(
        'functions' => array(
            'local_competency_linker_add_competency_to_module',
            'local_competency_linker_remove_competency_from_module',
            'local_competency_linker_set_module_competency_ruleoutcome'
        ),
        'restrictedusers' => 0,
        'enabled' => 1,
        'shortname' => 'competency_linker'
    )
);