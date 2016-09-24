#!/usr/bin/env python
#coding:utf-8
# Author:  Beining --<i@cnbeining.com>
# Purpose: Actions of onedrivecmd
# Created: 09/24/2016

import logging
from static import * 
from uploader import *
from helper_file import *
from helper_item import *
from session import * 

### Action
def do_init(client):
    """onedrivesdk.request.one_drive_client.OneDriveClient->onedrivesdk.request.one_drive_client.OneDriveClient
    
    Init of the script.
    
    Let user login, get the details, save the details in a conf file.
    
    Used at the first time login.
    """
    global VER, redirect_uri, client_secret, client_id, api_base_url, scopes

    auth_url = client.auth_provider.get_auth_url(redirect_uri)

    # Ask for the code
    print('')
    print(auth_url)
    print('')
    print('Paste this URL into your browser, approve the app\'s access.')
    print('Copy all the code in the new window, and paste it below:')

    code = input('Paste code here: ')

    client.auth_provider.authenticate(code, redirect_uri, client_secret)

    return client


def do_get(client, args):
    """OneDriveClient, [str] -> OneDriveClient
    
    Get a remote files information,
    then putput the link,
    or download it via the SDK's download method,
    or call aria2 to do the download.
    """
    
    link_list = []
    for f in args.rest:

        # get a file item
        item = get_remote_item(client, path = f)

        # some error handling
        if item is None:
            logging.warning('File {path} do not exist!'.format(path = f))
            break

        # fetch the file url, size and SHA1
        item_info = get_item_temp_download_info(item)

        # if only display the url
        if args.url:
            link_list.append(item_info[0])
            break

        local_name = path_to_name(f)

        # if hack, use aria2
        if args.hack:
            # the link still requires login
            #token = get_access_token(client)
            #header = 'Authorization: bearer {access_token}'.format(access_token = token)
            cmd = 'aria2c -c -o "{local_name}" -s16 -x16 -k1M "{remote_link}"'
            cmd = cmd.format(local_name = local_name,
                             remote_link = item_info[0], )
            #                 header = header)
            execute_cmd(cmd)
            break

        # if directly download, use the build in download() method
        # this method does not have any verbose so good luck with your
        # life downloading large files.
        # It would not be so miserble since OneDrive solely support filesize
        # as huge as 10GiB, and 2GiB for Business accounts. Yay!
        logging.info('Downloading {local_name}'.format(local_name = local_name))
        client.item(drive='me', id=item.id).download('./' + local_name)

    return client


def do_list(client, args):
    """OneDriveClient, [str] -> OneDriveClient
    
    List the content of a remote folder,
    with possbility of doing a recurrsive listing.
    
    If the user is using both flag recurrsive and multiple targets,
    or listing a huge drive at its root folder,
    the programme can just...crash. But who cares? I do not own Microsoft.
    """
    
    # recursive call
    if isinstance(args, list):
        folder_list = args
        is_recursive = True
    else:  #first call
        folder_list = args.rest
        is_recursive = args.recursive
        
    
    # Nothing provided. Instead of giving a error, list the root folder
    if folder_list == []:
        folder_list.append('/')
    
    for path in folder_list:
        # get the folder entry point
        folder = get_remote_item(client, path = path_to_remote_path(path))

        for i in folder:
            name = 'od:/' + i.name.encode('utf-8')
            if i.folder:
                # make a little difference so the user can notice
                name += '/'

                # handle recursive
                if is_recursive:
                    do_list(client, [get_remote_path_by_item(i)])

            # format as megacmd
            print('{name}\t{size}\t{created_date_time}'.format(name = name,
                                                               size = i.size,
                                                               created_date_time = i.created_date_time.strftime(i.DATETIME_FORMAT)))

    return client


def do_put(client, args):
    """OneDriveClient, [str] -> OneDriveClient
    
    Put local item(s) to a remote FOLDER.
    
    If no remote dir is specfied, will upload to root dir.
    
    A home brew uploading option is provided to show progress bar
    and manually adjust chunk size.
    
    The chunk size should be times of 320KiB, or shoot could happen:
    https://dev.onedrive.com/items/upload_large_files.htm#best-practices
    """
    # set target dir
    if not args.rest[-1].startswith('od:/'):
        from_list = args.rest
        target_dir = '/'

    else:
        from_list = args.rest[:-1]
        target_dir = args.rest[-1]
        
        # fix python cannot split path without / at end
        if not target_dir.endswith('/'):
            target_dir += '/'
    
    for i in from_list:
        # SDK one
        if not args.hack:
            client.item(drive="me", path=target_dir).upload_async(i)
            break

        # Home brew one, with progress bar
        else:
            upload_self(token = get_access_token(client),
                        source_file = i,
                        dest_path = target_dir,
                        chunksize= int(args.chunk))

    return client

def do_delete(client, args):
    """OneDriveClient, [str] -> OneDriveClient
    
    Move an item into trash bin.
    
    The folder must be empty before being deleted.
    
    There is currently NO WAY of permanently deleting an item via API/SDK.
    
    Somehow the SDK does not have this function.
    """
    for i in args.rest:
        if i.startswith('od:/'):  #is somewhere remote
            f = get_remote_item(client, path = i)
            
            #make the request, we have to do it ourselves
            req = requests.delete(api_base_url + 'drive/items/{id}'.format(id = f.id),
                                headers = {'Authorization': 'bearer {access_token}'.format(access_token = get_access_token(client)),})

    return client

def do_mkdir(client, args):
    """OneDriveClient, [str] -> OneDriveClient
    
    Make a remote folder.
    
    This is NOT a recursive one: the father folder must exist.

    Nice and easy.
    """
    for folder_path in args.rest:

        # make sure we are making the right folder
        if folder_path.endswith('/'):
            folder_path = folder_path[:-1]

        f = onedrivesdk.Folder()
        i = onedrivesdk.Item()

        i.name = path_to_name(folder_path)
        i.folder = f

        client.item(drive='me', path=path_to_remote_path(folder_path)).children.add(i)

    return client


def do_move(client, args):
    """OneDriveClient, [str] -> OneDriveClient

    Move a remote item to a remote location.

    Also can be used to rename.
    
    Not working so well....
    """
    from_location = args.rest[0]
    to_location = args.rest[1]
    
    # rename
    if path_to_remote_path(from_location) == path_to_remote_path(to_location):
        renamed_item = onedrivesdk.Item()
        renamed_item.name = path_to_name(to_location)

        get_bare_item_by_path(client, from_location).update(renamed_item)
        return client

    # real move
    moved_item = onedrivesdk.Item()
    to_item = get_bare_item_by_path(client, to_location)

    # if target is folder, put the item under
    if to_item.folder:
        moved_item.parent_reference = to_item
        get_bare_item_by_path(client, from_location).update(renamed_item)



if __name__=='__main__':
    unittest.main()