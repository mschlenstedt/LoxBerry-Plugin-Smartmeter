#!/usr/bin/php

<?php
// Copyright 2017 Michael Schlenstedt, michael@loxberry.de
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     http://www.apache.org/licenses/LICENSE-2.0
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

require_once	'php_sml_parser.class.php';

if ($argc != 2 || in_array($argv[1], array('--help', '-help', '-h', '-?'))) {
?>
This script will parse dumped SML data in HEX format.
  Usage: <?php echo $argv[0]; ?> <FILENAME>

<?php
exit(1);
} 

//$pathname='/var/run/shm/cgi/';
$filename=$argv[1];
$string = file_get_contents($filename);

$sml_parser = new SML_PARSER();

// Try to parse read data
$record = ($sml_parser->parse_sml_hexdata($string));

// If empty parser response, exit
if (!isset($record)) 
{
  exit(1);
} 
// Loop trough each parser result 
foreach ($record['body']['vallist'] as $values) 
{
	foreach($values as $key => $value) 
	{
		if ($key == "objName")
		{
			if ( $values['unit'] == "Wh" ) {
				echo $values['OBIS'] . "(" . ($values['value'] * $values['scaler'] / 1000) . "*" . "kWh)\n";
			} elseif (($values['unit'] == "W") && ($values['scaler'] <> 0)) {
				echo $values['OBIS'] . "(" . ($values['value'] * $values['scaler'] / 1000) . "*" . "kW)\n";
			} elseif (($values['unit'] == "W") && ($values['scaler'] == 0)) {
				echo $values['OBIS'] . "(" . ($values['value'] / 1000) . "*" . "kW)\n";
			} elseif (($values['unit'] == "V") && ($values['scaler'] <> 0)) {
				echo $values['OBIS'] . "(" . ($values['value'] * $values['scaler'] ) . "*" . "V)\n";
			} elseif (($values['unit'] == "A") && ($values['scaler'] <> 0)) {
				echo $values['OBIS'] . "(" . ($values['value'] * $values['scaler'] ) . "*" . "A)\n";
			} elseif (($values['unit'] == "Hz") && ($values['scaler'] <> 0)) {
				echo $values['OBIS'] . "(" . ($values['value'] * $values['scaler'] ) . "*" . "Hz)\n";
			} elseif (($values['unit'] == "Grad") && ($values['scaler'] <> 0)) {
				echo $values['OBIS'] . "(" . ($values['value'] * $values['scaler'] ) . "*" . "Grad)\n";
			} else {
				echo $values['OBIS'] . "(" . $values['value'] . "*" . $values['unit'] .")\n";
			}
		}  
	}
}

?>
