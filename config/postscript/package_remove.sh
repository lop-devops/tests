#!/bin/bash

package=('pep8' 'flake8' 'nose' 'nose2' 'epydoc' 'pylint' 'pexpect' 'netifaces' 'paramiko' 'enum' 'configparser')

for i in "${package[@]}"; 
do 
	echo "un install pip package "$i
	pip uninstall $i 
done
