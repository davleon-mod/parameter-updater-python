"""
Speckle Object Processor and Modifier

This script processes Speckle objects from a given URL, allowing for modification and updating of objects 
in Speckle streams. It handles the FE2 (Frontend v2) URL format and provides comprehensive object traversal
and modification capabilities.

Main functionalities:
- Parse Speckle FE2 URLs
- Authenticate with Speckle server
- Process and modify Speckle objects
- Create new commits with modified objects

Author: David Andres Leon 
Date: 11 Nov 2024
"""

from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_account_from_token
from specklepy.transports.server import ServerTransport
from specklepy.api import operations
from specklepy.objects import Base
import os
from dotenv import load_dotenv
import requests
import re

# Load environment variables
load_dotenv()
print("LOADING ENVIRONMENT VARIABLES")


changed_ids = []
same_ids =[]

def parse_speckle_url(url: str) -> dict:
    """
    Parse a Speckle Frontend v2 URL into its component parts.
    
    Args:
        url (str): The complete Speckle URL in FE2 format
                  Example: https://host/projects/[stream]/models/[branch]@[commit]
    
    Returns:
        dict: Dictionary containing server, stream_id, branch_name, and commit_id
              Returns None if parsing fails
    
    Example:
        >>> parse_speckle_url("https://speckle.xyz/projects/123/models/main@abc")
        {
            'server': 'speckle.xyz',
            'stream_id': '123',
            'branch_name': 'main',
            'commit_id': 'abc'
        }
    """
    try:
        pattern = r'https?://([^/]+)/projects/([^/]+)/models/([^@]+)@(.+)'
        match = re.match(pattern, url)
        
        if match:
            return {
                'server': match.group(1),
                'stream_id': match.group(2),
                'branch_name': match.group(3),
                'commit_id': match.group(4)
            }
        else:
            raise ValueError("URL format not recognized")
    except Exception as e:
        print(f"ERROR PARSING URL: {str(e)}")
        return None

def sanitize_server_url(url: str) -> str:
    """
    Sanitize a server URL to ensure proper formatting.
    
    Args:
        url (str): The server URL to sanitize
    
    Returns:
        str: Sanitized URL without double slashes or trailing slashes
    
    Example:
        >>> sanitize_server_url("https://speckle.xyz//")
        "speckle.xyz"
    """
    url = url.replace('http://', '').replace('https://', '')
    url = url.rstrip('/')
    url = url.replace('//', '/')
    return url

def get_safe_attribute(obj: object, attr: str) -> any:
    """
    Safely retrieve an attribute from an object without raising exceptions.
    
    Args:
        obj (object): The object to get the attribute from
        attr (str): The name of the attribute to retrieve
    
    Returns:
        any: The attribute value if it exists, None otherwise
    """
    try:
        return getattr(obj, attr, None)
    except:
        return None

def verify_token_and_permissions(client: SpeckleClient, stream_id: str, token: str) -> bool:
    """
    Verify that the provided token is valid and has necessary permissions.
    
    Args:
        client (SpeckleClient): The initialized Speckle client
        stream_id (str): The ID of the stream to verify access to
        token (str): The authentication token to verify
    
    Returns:
        bool: True if token is valid and has required permissions, False otherwise
    """
    try:
        user = client.active_user.get()
        print(f"AUTHENTICATED AS USER: {user.name if hasattr(user, 'name') else 'Unknown'}")
        
        stream = client.stream.get(stream_id)
        print(f"STREAM ACCESS VERIFIED: {stream.name}")
        
        return True
    except Exception as e:
        print(f"AUTHENTICATION/PERMISSION CHECK FAILED: {str(e)}")
        return False

def process_object(obj: Base, transport: ServerTransport, SpeckleId: str, target_key: str, target_value: str, depth: int = 0, 
                  max_depth: int = 10, processed: set = None) -> bool:
    """
    Process and potentially modify a Speckle object and its sub-objects.
    
    This function traverses through a Speckle object graph, processing each object
    and its children up to a maximum depth. It modifies the "test" parameter to the target value
    and handles circular references.
    
    Args:
        obj (Base): The Speckle object to process
        transport (ServerTransport): The transport being used
        target_value (str): The value to set for the "test" parameter
        depth (int): Current recursion depth
        max_depth (int): Maximum recursion depth to prevent infinite loops
        processed (set): Set of already processed object IDs
        
    Returns:
        bool: True if any changes were made, False otherwise
    """
    if processed is None:
        processed = set()
        
    changes_made = False
        
    if depth > max_depth:
        print(f"{'  ' * depth}MAX DEPTH REACHED")
        return changes_made
        
    if not isinstance(obj, Base):
        return changes_made
        
    obj_id = get_safe_attribute(obj, 'id')


    
    if obj_id and obj_id in processed:
        print(f"{'  ' * depth}ALREADY PROCESSED: {obj_id}")
        return changes_made
        
    if obj_id:
        processed.add(obj_id)
    
    indent = "  " * depth
    print(f"{indent}PROCESSING OBJECT: {obj_id or 'No ID'}")
    print(f"{indent}TYPE: {get_safe_attribute(obj, 'speckle_type') or 'Unknown type'}")
    
    # print obj_id and  SpeckleId


    if obj_id != SpeckleId:
        same_ids.append( obj_id)

    # if obj_id != SpeckleId:
    #     print(f"{'  ' * depth} SKIPPING OBJ: {obj_id}")
    #     return 

    # Process the test parameter if present
    if hasattr(obj, target_key):
        old_value = obj[target_key]
        obj[target_key] = target_value
        print(f"{indent}UPDATED TEST PARAMETER: '{old_value}' -> '{target_value}'")
        changed_ids.append(obj_id)
        changes_made = True
    
    # Process child objects
    try:
        # Get member names safely
        member_names = obj.get_member_names() if hasattr(obj, 'get_member_names') else []
        
        for name in member_names:
            try:
                value = getattr(obj, name)
                
                # Handle Base objects
                if isinstance(value, Base):
                    print(f"{indent}ENTERING SUB-OBJECT: {name}")
                    sub_changes = process_object(value, transport,SpeckleId,target_key ,target_value, depth + 1, max_depth, processed)
                    changes_made = changes_made or sub_changes
                
                # Handle lists of Base objects
                elif isinstance(value, list):
                    print(f"{indent}PROCESSING LIST: {name} ({len(value)} items)")
                    for i, item in enumerate(value):
                        if isinstance(item, Base):
                            print(f"{indent}PROCESSING LIST ITEM {i + 1}/{len(value)}")
                            sub_changes = process_object(item, transport, SpeckleId, target_key, target_value, depth + 1, max_depth, processed)
                            changes_made = changes_made or sub_changes
                            
            except Exception as e:
                print(f"{indent}ERROR PROCESSING MEMBER {name}: {str(e)}")
                continue
                
    except Exception as e:
        print(f"{indent}ERROR PROCESSING OBJECT: {str(e)}")
    
    return changes_made

def main():
    """
    Main execution function for the Speckle object processing script.
    
    This function:
    1. Parses a Speckle FE2 URL
    2. Authenticates with the Speckle server
    3. Processes and modifies the specified object
    4. Creates a new commit with the modified object
    
    Environment Variables Required:
        SPECKLE_TOKEN: Your Speckle authentication token
    """
    try:
        # The FE2 URL format - Replace this with your actual URL
        speckle_url = "https://app.speckle.systems/projects/f9eeb0be04/models/d3bcf9820c@ca5cde436f"
        url_parts = parse_speckle_url(speckle_url)
        
        if not url_parts:
            print("ERROR: COULD NOT PARSE SPECKLE URL")
            return
            
        # Get credentials from environment variables 
        token = os.getenv('SPECKLE_TOKEN')
        server = url_parts['server']
        
        if not token:
            print("ERROR: MISSING SPECKLE_TOKEN ENVIRONMENT VARIABLE")
            return
        
        print("CONNECTING TO SPECKLE SERVER:", server)
        print("STREAM ID:", url_parts['stream_id'])
        print("BRANCH:", url_parts['branch_name'])
        print("COMMIT:", url_parts['commit_id'])
        
        # Initialize Speckle client
        try:
            client = SpeckleClient(host=server)
            account = get_account_from_token(token, server)
            client.authenticate_with_account(account)
            print("AUTHENTICATION SUCCESSFUL")
        except Exception as e:
            print(f"AUTHENTICATION FAILED: {str(e)}")
            return

        # Verify permissions
        if not verify_token_and_permissions(client, url_parts['stream_id'], token):
            print("PERMISSION VERIFICATION FAILED")
            return
            
        # Create transport with explicit authentication
        transport = ServerTransport(
            stream_id=url_parts['stream_id'],
            account=account,
            url=f"https://{server}"
        )
        
        # Get commit object
        try:
            commit = client.commit.get(url_parts['stream_id'], url_parts['commit_id'])
            if not commit:
                print("ERROR: COULD NOT FIND SPECIFIED COMMIT")
                return
            obj_id = commit.referencedObject
            print("REFERENCED OBJECT ID:", obj_id)
        except Exception as e:
            print(f"ERROR GETTING COMMIT: {str(e)}")
            return
            
        # Receive and process object
        try:
            print("\nRECEIVING OBJECT...")
            obj = operations.receive(obj_id, remote_transport=transport)
            print("OBJECT RECEIVED SUCCESSFULLY")
            
            print("\nPROCESSING OBJECT...")

            ####
            process_object(obj, transport, 'the_specl', "SF_GEN_Weight_t", "200") ### here you update the parameter value for "test"
           
           
           
           
           
           #################
           
            print("OBJECT PROCESSING COMPLETE")
            
        except Exception as e:
            print(f"ERROR RECEIVING/PROCESSING OBJECT: {str(e)}")
            return
            
        # Send modified object
        try:
            print("\nSAVING MODIFIED OBJECT...")
            print("DEBUG - Server URL:", transport.url)
            print("DEBUG - Stream ID:", transport.stream_id)
            
            # Verify stream exists before sending
            stream = client.stream.get(url_parts['stream_id'])
            if not stream:
                print(f"ERROR: STREAM {url_parts['stream_id']} NOT FOUND")
                return
            print("VERIFIED STREAM EXISTS:", stream.name)
            
            new_obj_id = operations.send(obj, [transport])
            print("NEW OBJECT SAVED WITH ID:", new_obj_id)
            
            # Create new commit on the same branch
            new_commit = client.commit.create(
                stream_id=url_parts['stream_id'],
                object_id=new_obj_id,
                branch_name=url_parts['branch_name'],
                message="Updated userStrings.test value to 'test2'"
            )
            print("NEW COMMIT CREATED WITH ID:", new_commit)
            print("\nPROCESS COMPLETED SUCCESSFULLY")
            print("CHANGED OBJECT IDS:", changed_ids)
            print("SAME OBJECT IDS:", same_ids)
            
            
        except requests.exceptions.HTTPError as e:
            print(f"HTTP ERROR DURING SEND: {str(e)}")
            if e.response.status_code == 401:
                print("AUTHENTICATION ERROR - CHECK TOKEN AND PERMISSIONS")
            elif e.response.status_code == 403:
                print("PERMISSION DENIED - NO ACCESS TO THIS STREAM")
            else:
                print(f"SERVER RETURNED STATUS CODE: {e.response.status_code}")
            return
        except Exception as e:
            print(f"ERROR DURING SEND/COMMIT: {str(e)}")
            return

    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {str(e)}")
        raise

if __name__ == "__main__":
    """
    Script entry point. Executes the main function and handles any top-level exceptions.
    
    Usage:
        1. Set up your environment variables in a .env file:
           SPECKLE_TOKEN=your-token-here
        
        2. Replace the speckle_url in main() with your target URL
        
        3. Run the script:
           python script_name.py
    """
    main()