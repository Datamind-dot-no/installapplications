#!/usr/bin/python
# -*- coding: utf-8 -*-

# Generate Json file for installapplications
# Usage: python generatejson.py --item \
# item-name='A name' \
# item-path='A path' \
# item-stage='A stage' \
# item-type='A type' \
# item-url='A url' \
# script-do-not-wait='A boolean' \
# --base-url URL \
# --output PATH

#
# --item can be used unlimited times
#
# --input looks inside a base folder which you setup for a installapplications 
#     webserver, dives in the installapplications folder you've prepared for upload to 
#     the server, and snaps up the packages you have put in folders for each of the stages
#     and uses these as items.
# Future plan is to add the options for each of the items to a template plist in 
#     the --input base folder
# Next future plan for this tool is to add AWS S3 integration for auto-upload

import hashlib
import json
import argparse
import os
import subprocess
import tempfile
from xml.dom import minidom


def gethash(filename):
    hash_function = hashlib.sha256()
    if not os.path.isfile(filename):
        return 'NOT A FILE'

    fileref = open(filename, 'rb')
    while 1:
        chunk = fileref.read(2**16)
        if not chunk:
            break
        hash_function.update(chunk)
    fileref.close()
    return hash_function.hexdigest()


def getpkginfopath(filename):
    '''Extracts the package BOM with xar'''
    cmd = ['/usr/bin/xar', '-tf', filename]
    proc = subprocess.Popen(cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    (bom, err) = proc.communicate()
    bom = bom.strip().split('\n')
    if proc.returncode == 0:
        for entry in bom:
            if entry.startswith('PackageInfo'):
                return entry
            elif entry.endswith('.pkg/PackageInfo'):
                return entry
    else:
        print "Error: %s while extracting BOM for %s" % (err, filename)


def extractpkginfo(filename):
    '''Takes input of a file path and returns a file path to the
    extracted PackageInfo file.'''
    cwd = os.getcwd()

    if not os.path.isfile(filename):
        return
    else:
        tmpFolder = tempfile.mkdtemp()
        os.chdir(tmpFolder)
        # need to get path from BOM
        pkgInfoPath = getpkginfopath(filename)

        extractedPkgInfoPath = os.path.join(tmpFolder, pkgInfoPath)
        cmd = ['/usr/bin/xar', '-xf', filename, pkgInfoPath]
        proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        out, err = proc.communicate()
        os.chdir(cwd)
        return extractedPkgInfoPath


def getpkginfo(filename):
    '''Takes input of a file path and returns strings of the
    package identifier and version from PackageInfo.'''
    if not os.path.isfile(filename):
        return "", ""

    else:
        pkgInfoPath = extractpkginfo(filename)
        dom = minidom.parse(pkgInfoPath)
        pkgRefs = dom.getElementsByTagName('pkg-info')
        for ref in pkgRefs:
            pkgId = ref.attributes['identifier'].value.encode('UTF-8')
            pkgVersion = ref.attributes['version'].value.encode('UTF-8')
            return pkgId, pkgVersion




def getitems(folder, stages):
    '''Takes input of a folder path and returns an array of key and value pairs
    for the packages and scripts items found in the subfolders for each stage.
    Set defaults for the other itemOptions.'''
    print 'Scanning input folder %s' % str(folder) 
    if not os.path.isdir(folder):
        return []
    else:
        itemsToProcess = []
#         for filename in os.listdir(directory):
#             if filename.endswith(".asm") or filename.endswith(".py"): 
#                 # print(os.path.join(directory, filename))
#                 continue
#             else:
#                 continue    
        for stageFolder in stages:
            theFolder = '%s/%s' % (folder, stageFolder)
            for path, subfolders, files in os.walk(theFolder):
                for name in files:
                    processedItem = {}
                    processedItem['item-path'] = os.path.join(path, name)
                    print processedItem['item-path']
                    processedItem['item-name'] = ''
                    processedItem['item-stage'] = stageFolder
                    print processedItem['item-stage']
                    processedItem['item-type'] = ''
                    processedItem['item-url'] = ''
                    processedItem['script-do-not-wait'] = 'False'
                    itemsToProcess.append(processedItem)
    return itemsToProcess
        

def main():
    # current dir to be used as default for --input and --output 
    cwd = os.getcwd()
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True, default=None, action='store',
                        help='Base URL to where root dir is hosted')
    parser.add_argument('--input', required=False, default=cwd, action='store',
                        help='Input folder to fetch items from. \
                        You can put your packages and scripts in this path,  \
                        in subfolders named after the stages they are to be \
                        installed or run in. \
                        Defaults to current working folder.')
    parser.add_argument('--output', required=False, default=cwd, action='store',
                        help='Output folder to save json \
                        Defaults to current working folder.')
    parser.add_argument('--item', required=False, default=None, action='append', nargs=6,
                        metavar=(
                            'item-name', 'item-path', 'item-stage',
                            'item-type', 'item-url', 'script-do-not-wait'),
                        help='Item argument and its options. Used to spefify item directly \
                        in the script invocation instead of using the the --input \
                        argument. When using --item, all options are required. Add each \
                        option in format --<option> <value> Setting\
                        --scipt-do-not-wait defaults to rootscript and \
                        --item-stage defaults to userland')  
    args = parser.parse_args()

    
    # Bail if we don't have the base url
    if not args.base_url:
        parser.print_help()
        exit(1)

    # Create our stages now so InstallApplications won't blow up
    stages = {
        'preflight': [],
        'setupassistant': [],
        'userland': []
    }

    if not args.item:
        # When no items were passed, assume we're using an input folder
        itemsToProcess = getitems(args.input, stages)
        if not itemsToProcess:
            print 'No items found to process in %s' % args.input
            exit(1)
    else:
        # Let's first loop through the items and convert everything to key value
        # pairs
        itemsToProcess = []
        for item in args.item:
            processedItem = {}
            for itemOption in item:
                values = itemOption.split('=')
                processedItem[values[0]] = values[1]
            itemsToProcess.append(processedItem)

    # Process each item in the order they were passed in
    for item in itemsToProcess:
        itemJson = {}
        # Get the file extension of the file
        fileExt = os.path.splitext(item['item-path'])[1]
        # Get the file name of the file
        fileName = os.path.basename(item['item-path'])
        # Get the full path of the file
        filePath = item['item-path']

        # Determine the type of item to process - for scripts, default to
        # rootscript
        if fileExt in ('.py', '.sh', '.rb', '.php'):
            if item['item-type']:
                itemJson['type'] = itemType = item['item-type']
            else:
                itemJson['type'] = itemType = 'rootscript'
        elif fileExt == '.pkg':
            itemJson['type'] = itemType = 'package'
        else:
            print 'Could not determine package type for item or unsupported: \
            %s' % str(item)
            exit(1)
        if itemType not in ('package', 'rootscript', 'userscript'):
            print 'item-type malformed: %s' % str(item['item-type'])
            exit(1)

        # Determine the stage of the item to process - default to userland
        if item['item-stage']:
            if item['item-stage'] in ('preflight', 'setupassistant',
                                      'userland'):
                itemStage = item['item-stage']
                pass
            else:
                print 'item-stage malformed: %s' % str(item['item-stage'])
                exit(1)
        else:
            itemStage = 'userland'

        # Determine the url of the item to process - defaults to
        # baseurl/stage/filename
        if not item['item-url']:
            itemJson['url'] = '%s/%s/%s' % (args.base_url, itemStage, fileName)
        else:
            itemJson['url'] = item['item-url']

        # Determine the name of the item to process - defaults to the filename
        if not item['item-name']:
            itemJson['name'] = fileName
        else:
            itemJson['name'] = item['item-name']

        # Determine the hash of the item to process - SHA256
        itemJson['hash'] = gethash(filePath)

        # Add information for scripts and packages
        if itemType in ('rootscript', 'userscript'):
            if itemType == 'userscript':
                # Pass the userscripts folder path
                itemJson['file'] = '/Library/Application Support/'\
                    'installapplications/userscripts/%s' % fileName
            else:
                itemJson['file'] = '/Library/Application Support/'\
                    'installapplications/%s' % fileName
            # Check crappy way of doing booleans
            if item['script-do-not-wait'] in ('true', 'True', '1',
                                              'false', 'False', '0'):
                # If True, pass the key to the item
                if item['script-do-not-wait'] in ('true', 'True', '1'):
                    itemJson['donotwait'] = True
            else:
                print 'script-do-not-wait malformed: %s ' % str(
                    item['script-do-not-wait'])
                exit(1)
        # If packages, we need the version and packageid
        elif itemType == 'package':
            (pkgId, pkgVersion) = getpkginfo(filePath)
            itemJson['file'] = '/Library/Application Support/'\
                'installapplications/%s' % fileName
            itemJson['packageid'] = pkgId
            itemJson['version'] = pkgVersion

        # Append the info to the appropriate stage
        stages[itemStage].append(itemJson)

    # Saving the json file to the output directory path
    if args.output:
        savePath = os.path.join(args.output, 'bootstrap.json')
    else:
        savePath = os.path.join(rootdir, 'bootstrap.json')

    # Sort the primary keys, but not the sub keys, so things are in the correct
    # order
    try:
        with open(savePath, 'w') as outFile:
            json.dump(stages, outFile, sort_keys=True, indent=2)
    except IOError:
        print '[Error] Not a valid directory: %s' % savePath
        exit(1)

    print 'Json saved to %s' % savePath


if __name__ == '__main__':
    main()
