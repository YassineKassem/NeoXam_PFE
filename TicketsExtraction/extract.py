import requests
import json
import time
import pandas as pd
from datetime import datetime
from collections import defaultdict
 
def fetch_jira_issues(jira_url, project_key, cookie_value, max_issues=None):
    """
    Fetches Jira issues for a specific project using Jira REST API v2 with Cookie authentication
    Including comments, resolution information, and release notes in the same request
 
    Args:
        jira_url (str): Base URL of your Jira instance (e.g., "https://your-domain.atlassian.net")
        project_key (str): The project key to fetch issues for (e.g., "PROJ")
        cookie_value (str): Your Jira session cookie value (typically named JSESSIONID or cloud.session.token)
        max_issues (int, optional): Maximum number of issues to fetch. If None, fetch all issues.
 
    Returns:
        list: List of Jira issues fetched
    """
    # Initialize variables
    all_issues = []
    batch_size = 100  # Jira's maximum batch size is typically 100
    start_at = 0
 
    # Set a flag to indicate whether we're fetching all issues or a limited number
    fetch_all = max_issues is None
    target_count = float('inf') if fetch_all else max_issues
 
    # Headers with Cookie authentication
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": cookie_value
    }
 
    # Get total number of issues first
    endpoint = f"{jira_url}/rest/api/2/search"
    jql = f"project = {project_key} ORDER BY created DESC"
    initial_payload = {
        "jql": jql,
        "maxResults": 0  # We just want the total count initially
    }
 
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            data=json.dumps(initial_payload)
        )
 
        if response.status_code != 200:
            print(f"Error getting issue count: {response.status_code}")
            print(response.text)
            return all_issues
 
        total_available = response.json()["total"]
        total_to_fetch = total_available if fetch_all else min(max_issues, total_available)
        print(f"Total issues found: {total_available}, Will fetch: {total_to_fetch}")
 
    except Exception as e:
        print(f"An error occurred while getting issue count: {str(e)}")
        return all_issues
 
    # Continue fetching until we've reached the target count
    while len(all_issues) < total_to_fetch:
        # Payload - added customfield_13570 for release notes
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": min(batch_size, total_to_fetch - len(all_issues)),
            "fields": [
                "summary",
                "description",
                "issuetype",
                "status",
                "priority",
                "created",
                "updated",
                "reporter",
                "assignee",
                "labels",
                "components",
                "comment",
                "resolution",  # Resolution field
                "resolutiondate",  # When it was resolved
                "issuelinks",  # Linked issues
                "versions", #Affects Version/s
                "fixVersions",  # Versions where the issue was fixed
                "customfield_13751", # target versions
                "customfield_13570",  # Release Note custom field
                "subtasks",  # Subtasks information
                "watches",  # Number of watchers
                "duedate",  # Due date if set
                "parent",  # Parent issue if this is a subtask
                "customfield_19850", #Module - Feature,
                "worklog" #work logs
            ]
        }
 
        try:
            # Make API request
            response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload)
            )
 
            # Check if request was successful
            if response.status_code == 200:
                data = response.json()
 
                # If no issues returned, we've fetched all available issues
                if len(data["issues"]) == 0:
                    print(f"All available issues fetched. Total: {len(all_issues)}")
                    break
 
                # Add issues to our list
                all_issues.extend(data["issues"])
                print(
                    f"Fetched {len(data['issues'])} issues. Progress: {len(all_issues)}/{total_to_fetch} ({(len(all_issues) / total_to_fetch * 100):.1f}%)")
 
                # Update start_at for the next batch
                start_at += len(data["issues"])
 
                # Sleep to prevent hitting rate limits
                time.sleep(1)
            else:
                print(f"Error fetching issues: {response.status_code}")
                print(response.text)
                break
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            break
 
    return all_issues
 
def process_comments(comment_field):
    """
    Processes the comment field to create a formatted string
 
    Args:
        comment_field (dict): Comment field from Jira issue
 
    Returns:
        str: Formatted string with all comments
    """
    if not comment_field or not comment_field.get("comments"):
        return ""
 
    comments = comment_field.get("comments", [])
    formatted_comments = []
 
    for comment in comments:
        author = comment.get("author", {}).get("displayName", "Unknown")
        created = comment.get("created", "Unknown date")
        body = comment.get("body", "No content")
        formatted_comment = f"[{created}] {author}: {body}"
        formatted_comments.append(formatted_comment)
 
    return "\n---\n".join(formatted_comments)
 
 
def process_issue_links(issuelinks):
    """
    Process issue links to create a formatted string
 
    Args:
        issuelinks (list): List of issue links
 
    Returns:
        str: Formatted string with all linked issues
    """
    if not issuelinks:
        return ""
 
    formatted_links = []
 
    for link in issuelinks:
        if "outwardIssue" in link:
            relation = link.get("type", {}).get("outward", "relates to")
            linked_issue = link.get("outwardIssue", {})
            direction = "outward"
        elif "inwardIssue" in link:
            relation = link.get("type", {}).get("inward", "is related to by")
            linked_issue = link.get("inwardIssue", {})
            direction = "inward"
        else:
            continue
 
        key = linked_issue.get("key", "Unknown")
        status = linked_issue.get("fields", {}).get("status", {}).get("name",
                                                                      "Unknown status") if "fields" in linked_issue else "Unknown status"
        summary = linked_issue.get("fields", {}).get("summary",
                                                     "No summary") if "fields" in linked_issue else "No summary"
 
        formatted_link = f"{direction}: {relation} {key} [{status}] - {summary}"
        formatted_links.append(formatted_link)
 
    return "\n".join(formatted_links)
 
 
def process_subtasks(subtasks):
    """
    Process subtasks to create a formatted string
 
    Args:
        subtasks (list): List of subtasks
 
    Returns:
        str: Formatted string with all subtasks
    """
    if not subtasks:
        return ""
 
    formatted_subtasks = []
 
    for subtask in subtasks:
        key = subtask.get("key", "Unknown")
        status = subtask.get("fields", {}).get("status", {}).get("name",
                                                                 "Unknown status") if "fields" in subtask else "Unknown status"
        summary = subtask.get("fields", {}).get("summary", "No summary") if "fields" in subtask else "No summary"
 
        formatted_subtask = f"{key} [{status}] - {summary}"
        formatted_subtasks.append(formatted_subtask)
 
    return "\n".join(formatted_subtasks)
 
 
def process_fix_versions(fix_versions):
    """
    Process fix versions to create a formatted string
 
    Args:
        fix_versions (list): List of fix versions
 
    Returns:
        str: Formatted string with all fix versions
    """
    if not fix_versions:
        return ""
 
    return ", ".join([version.get("name", "Unknown") for version in fix_versions])
def process__versions(versions):
    """
    Process fix versions to create a formatted string
 
    Args:
        fix_versions (list): List of fix versions
 
    Returns:
        str: Formatted string with all fix versions
    """
    if not versions:
        return ""
 
    return ", ".join([version.get("name", "Unknown") for version in versions])
# def process_worklog(worklog):
#     """
#     Processes the worklog field to create a formatted string or list of worklogs
 
#     Args:
#         worklog (list): List of worklog entries
 
#     Returns:
#         list: Formatted list with worklog information
#     """
#     if not worklog:
#         return []
 
#     formatted_worklog = []
 
#     for entry in worklog:
#         author = entry.get("author", {}).get("displayName", "Unknown")
#         time_spent = entry.get("timeSpent", "Unknown time")
#         created = entry.get("created", "Unknown date")
#         comment = entry.get("comment", "No comment")
 
#         formatted_entry = {
#             "Author": author,
#             "Time Spent": time_spent,
#             "Created": created,
#             "Comment": comment
#         }
#         formatted_worklog.append(formatted_entry)
 
#     return formatted_worklog
 
 
def convert_seconds_to_hm(seconds):
    """
    Convertit un nombre de secondes en un format "Xh Ym" (heures et minutes).
   
    Paramètre :
        seconds (int): Le nombre de secondes à convertir.
       
    Retour :
        str: Le temps formaté en heures et minutes "Xh Ym".
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"
 
def calculer_temps_par_collaborateur(worklog):
    """
    Cette fonction prend un worklog et retourne un dictionnaire avec le temps total passé par chaque collaborateur
    sous forme de chaîne formatée "Xh Ym" en utilisant le champ "timeSpentSeconds".
   
    Paramètres :
        worklog (list): Une liste de worklogs pour un ticket donné.
       
    Retour :
        dict: Un dictionnaire avec les noms des collaborateurs comme clés et le temps travaillé formaté comme valeur.
    """
    # Dictionnaire pour accumuler le temps total en secondes pour chaque collaborateur
    temps_par_collaborateur = defaultdict(int)
 
    # Parcourir les worklogs et additionner le temps en secondes
    for entry in worklog:
        author = entry.get("author", {}).get("displayName", "Inconnu")
        time_spent_seconds = entry.get("timeSpentSeconds", 0)  # Récupère le temps passé en secondes
       
        # Ajouter les secondes au total pour chaque collaborateur
        temps_par_collaborateur[author] += time_spent_seconds
 
    # Dictionnaire pour stocker le temps travaillé formaté pour chaque collaborateur
    temps_travaille_formatte = {}
 
    # Convertir les secondes en heures et minutes formatées
    for author, total_seconds in temps_par_collaborateur.items():
        temps_travaille_formatte[author] = convert_seconds_to_hm(total_seconds)
   
    return temps_travaille_formatte
def save_to_csv(issues, output_file="jira_issues.csv"):
    """
    Saves extracted issues to a CSV file
 
    Args:
        issues (list): List of Jira issues
        output_file (str): Output filename
    """
    # Convert issues to a simplified format for CSV
    processed_issues = []
 
    for issue in issues:
        # Extract fields
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        #print(fields)
 
        # Get values, handling possible None values
        issue_type = fields.get("issuetype", {}).get("name", "") if fields.get("issuetype") else ""
        summary = fields.get("summary", "")
        description = fields.get("description", "")
        status = fields.get("status", {}).get("name", "") if fields.get("status") else ""
        priority = fields.get("priority", {}).get("name", "") if fields.get("priority") else ""
        created = fields.get("created", "")
        updated = fields.get("updated", "")
        reporter = fields.get("reporter", {}).get("displayName", "") if fields.get("reporter") else ""
        assignee = fields.get("assignee", {}).get("displayName", "") if fields.get("assignee") else ""
 
        # Get resolution information
        resolution = fields.get("resolution", {}).get("name", "") if fields.get("resolution") else "Unresolved"
        resolution_date = fields.get("resolutiondate", "")
 
        # Get release note
        release_note = fields.get("customfield_13570", "")
 
        #Get Module Feature
        target_version = fields.get("customfield_13751")
        #if isinstance(module_feature, dict):
        #    module_feature = module_feature.get("value", "")
        #else:
        #    module_feature = ""
 
        #print(module_feature)
        # Get labels and components as comma-separated strings
        labels = ", ".join(fields.get("labels", []))
        components = ", ".join([c.get("name", "") for c in fields.get("components", [])])
 
        versions = process__versions(fields.get("versions", []))
 
        # Process fix versions
        fix_versions = process_fix_versions(fields.get("fixVersions", []))
 
        module_feature = fields.get("customfield_19850")
 
        # Process issue links
        issue_links = process_issue_links(fields.get("issuelinks", []))
 
        # Process subtasks
        subtasks = process_subtasks(fields.get("subtasks", []))
 
        # Get parent issue if it's a subtask
        parent = fields.get("parent", {}).get("key", "") if fields.get("parent") else ""
 
        # Get due date if set
        due_date = fields.get("duedate", "")
 
 
        # Get watchers count
        watches = fields.get("watches", {}).get("watchCount", 0) if fields.get("watches") else 0
 
        # Process comments
        comments = process_comments(fields.get("comment"))
 
        worklog = calculer_temps_par_collaborateur(fields.get("worklog", {}).get("worklogs", []))
           
        processed_issue = {
            "Key": key,
            "Type": issue_type,
            "Summary": summary,
            "Description": description,
            "Status": status,
            "Resolution": resolution,
            "Resolution Date": resolution_date,
            "Release Note": release_note,
            "Priority": priority,
            "Created": created,
            "Updated": updated,
            "Due Date": due_date,
            "Reporter": reporter,
            "Assignee": assignee,
            "Labels": labels,
            "Components": components,
            "Versions":versions,
            "Fix Versions": fix_versions,
            "Target Version":target_version,
            "Parent Issue": parent,
            "Watchers": watches,
            "Issue Links": issue_links,
            "Subtasks": subtasks,
            "Comments": comments,
            "Module-Feature": module_feature,
            "Worklog": worklog  # Include the processed worklog
 
        }
 
        processed_issues.append(processed_issue)
 
    # Create DataFrame and save to CSV
    df = pd.DataFrame(processed_issues)
    df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"Saved {len(processed_issues)} issues to {output_file}")
 
 
def main():
    # Jira configuration - replace with your values
    jira_url = "https://nx-jira8.my-nx.com/"
    project_key = "DHRD"
 
    # Cookie authentication value - this should include the cookie name and value
    # Example: "JSESSIONID=ABC123DEF456; atlassian.xsrf.token=XYZ-789"
    cookie_value = "JSESSIONID=6B60697AFF34EF9CF025A59AA505BF91; seraph.rememberme.cookie=290740%3A0abd5b01e6a381aa5a1ef9672172893ca788357f; atlassian.xsrf.token=ASFX-EHQK-UFFZ-52VS_4baf53150c8b7c9f31d64637296ac6184f8fe5d2_lin"
    # Fetch issues (including comments in the same request)
 
    # Fetch issues (including comments in the same request)
    # Pass None to max_issues to fetch all available issues
    issues = fetch_jira_issues(jira_url, project_key, cookie_value, max_issues=None)
 
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"jira_issues_{project_key}_{timestamp}.csv"
 
    # Save issues to CSV
    save_to_csv(issues, output_file)
 
 
if __name__ == "__main__":
    main()
 