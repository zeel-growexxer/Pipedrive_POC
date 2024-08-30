
import streamlit as st
import openai
from io import StringIO


import requests
import json
from langchain.chains import LLMChain
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq
import re
import configparser
import openai
import warnings
warnings.filterwarnings('ignore')



def read_config(filename):
    config = configparser.ConfigParser()
    config.read(filename)
    return config['API']


config = read_config('new_api_keys.ini')
api_token = config['pipedrive_api_token']
api_key = config['groq_api_key']
openAI_key = config['openAI_key']


# # **FOR CLASSIFICATION OF USER QUERY**

# ## **USING OPENAI**


openai.api_key = openAI_key

classification_prompt_template = """
Rules:
1. **Primary Action Focus**: Always prioritize the main action in the query.
   - If the main action is to create or update a 'person', classify only as 'person', even if other details like 'organization' or 'deal' are mentioned.
   - If the main action is to create or update an 'activity', classify only as 'activity', even if other details like 'deal', 'person', 'stage', or 'organization' are mentioned.
   - If the main action is to create or update a 'deal', classify only as 'deal', even if other details like 'person', 'stage', or 'organization' are mentioned.
   Examples:
   - "Create a new person named Sharon, including the email address sharon@example.com, phone number 85793048, and organization ID 10." -> 'person'
   - "Can you create an activity? It should be due by tomorrow and titled 'Activity-New' for deal ID 2" -> 'activity'
   - "add activity with subject as testing_final_code having org id = 10, person id = 2, type as lunch and due date as 31st august 2024" -> 'activity'
   - "I need to initiate a new deal, and it should be titled 'Deal1'" -> 'deal'
   - "create a deal having title as 'new_check-deal' in org id of 4, stage id of 2 and with person id 11" -> 'deal'
   - "update deal 3, org id 4, person id 20, stage id 2" -> 'deal'
2. **'Participant' vs 'Person'**: Distinguish between 'participant' and 'person'. Do not classify 'participant' as 'person'.

Instructions:
Given the user query, identify the relevant components. The components could be 'activity', 'stage', 'deal', 'person', or 'organization'. Focus on the primary action of the query. If multiple components are involved, list them clearly, but ensure:
   - For queries involving the creation or updating of a person, only 'person' should be identified, ignoring other details.
   - For queries involving the creation or updating of an activity, only 'activity' should be identified, ignoring other details.

Important:
The following examples should return the specified output:
Examples:
"Who are participants in deal 4?" -> 'deal'
"Add a participant with ID 6 to deal ID 8." -> 'deal'
"Delete participant with ID 7 from deal 19." -> 'deal'
"Create a new person named Sharon, including the email address sharon@example.com, phone number 85793048, and organization ID 10." -> 'person'
"List all persons associated with deal 3." -> 'person', 'deal'
"Can you retrieve the details of all deals currently associated with stage 3?" -> 'deal', 'stage'
"Add a stage named 'last-stage' to the pipeline with ID 1." -> 'stage'
"Produce a detailed timeline for our deals from January 1st, 2024, broken down into daily segments, emphasizing the dates they were won." -> 'deal'
"I need all activities logged for the 3rd deal." -> 'activity', 'deal'
Query: {user_query}
"""

def classify_query(user_query):
    prompt = classification_prompt_template.format(user_query=user_query)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            temperature=0
        )
        llm_response = response['choices'][0]['message']['content'].strip().lower()

        components = []
        if "activity" in llm_response:
            components.append("activity")
        if "stage" in llm_response:
            components.append("stage")
        if "deal" in llm_response:
            components.append("deal")
        if "person" in llm_response:
            components.append("person")
        if "organization" in llm_response:
            components.append("organization")
        return components

    except Exception as e:
        st.write(f"An error occurred during classification: {e}")
        return ["unknown"]

def handle_multi_component_query(user_query, components):
    if 'stage' in components and 'deal' in components:
        handle_stage_query(user_query)
    elif 'activity' in components and 'deal' in components:
        handle_deal_query(user_query)
    elif 'person' in components and 'deal' in components:
        handle_person_query(user_query)
    elif 'activity' in components and 'person' in components:
        handle_person_query(user_query)
    elif 'activity' in components and 'organization' in components:
        handle_organization_query(user_query)
    elif 'person' in components and 'organization' in components:
        handle_organization_query(user_query)
    elif 'deal' in components and 'organization' in components:
        handle_organization_query(user_query)
    else:
        st.write("Could not classify the query. Please refine your query.")


# # **ACTIVITY**


def ask_for_missing_details_activity(activity_details, selected_options):
    prompts = {
        'subject': "Please provide the subject of the activity.",
        'deal_id': "Please provide the deal ID associated with this activity.",
        'person_id': "Please provide the person ID associated with this activity.",
        'org_id': "Please provide the organization ID associated with this activity.",
        'due_date': "Please provide the due date for this activity (format YYYY-MM-DD).",
        'type': "Please specify the type of activity (e.g., call, meeting).",
        'due_time': "Please provide the due time for this activity (format HH:MM).",
        'participants': "Please provide a list of participants (format: person_id=5, primary_flag=True; person_id=7, primary_flag=False)."
    }

    field_options = {
        '1': 'subject',
        '2': 'deal_id',
        '3': 'person_id',
        '4': 'org_id',
        '5': 'due_date',
        '6': 'type',
        '7': 'due_time',
        '8': 'participants'
    }

    for option in selected_options:
        field = field_options.get(option)
        if field and field not in activity_details:
            activity_details[field] = st.text_input(prompts[field], key=field)

    if 'participants' in activity_details:
        participants = []
        for participant in activity_details['participants'].split(';'):
            person_id, primary_flag = participant.split(',')
            person_id = int(person_id.split('=')[1].strip())
            primary_flag = primary_flag.split('=')[1].strip().lower() == 'true'
            participants.append({"person_id": person_id, "primary_flag": primary_flag})
        activity_details['participants'] = participants

    return activity_details

def prompt_for_activity_details():
    st.write("Select options to add/modify details:")
    st.write("1. Subject")
    st.write("2. Deal ID")
    st.write("3. Person ID")
    st.write("4. Organization ID")
    st.write("5. Due Date")
    st.write("6. Type")
    st.write("7. Due Time")
    st.write("8. Participants")
    st.write("If you do not want to add/modify anything, enter none")
    st.write("Enter numbers separated by commas (e.g., 1,3,5): ")
    user_input = st.text_input('Enter your input:', value='').strip().lower()

    if user_input == "none":
        return {}

    selected_options = [opt.strip() for opt in user_input.split(',')]
    return ask_for_missing_details_activity({}, selected_options)



def get_all_activities():
    url = f'https://api.pipedrive.com/v1/activities?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def get_activity_by_id(activity_id):
    url = f'https://api.pipedrive.com/v1/activities/{activity_id}?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def create_activity(data=None):
    if data is None or not data:
        data = prompt_for_activity_details()

    url = f'https://api.pipedrive.com/v1/activities?api_token={api_token}'
    st.write("Data being sent to API:", json.dumps(data, indent=4))
    response = requests.post(url, json=data)
    return response.json()

def update_activity(activity_id, new_values=None):
    if new_values is None:
        new_values = {}

    if not new_values:
        st.write("No fields to update provided.")
        new_values = prompt_for_activity_details()

    url = f'https://api.pipedrive.com/v1/activities/{activity_id}?api_token={api_token}'
    st.write("Data being sent to API:", json.dumps(new_values, indent=4))
    response = requests.put(url, json=new_values)

    return response.json()

def delete_activity(activity_id):
    url = f'https://api.pipedrive.com/v1/activities/{activity_id}?api_token={api_token}'
    response = requests.delete(url)
    return response.json()

def parse_llm_response(llm_response):
    llm_response = llm_response.strip().lower()
    parts = map(str.strip, llm_response.split(","))

    method_name = next(parts, "").strip()
    params = {}

    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip()] = value.strip()
        elif part.isdigit():
            params['id'] = part
        elif part in ['yes', 'no']:
            params['rotten_flag'] = part

    return method_name, params



def handle_activity_query(user_query):
    prompt_template = """
    You are an AI assistant for interacting with the Pipedrive API. Based on the user's query, return the exact method name and any relevant parameters as a comma-separated list. Only use the following method names:
    - "get all activities"
    - "get activity by id"
    - "create activity"
    - "update activity"
    - "delete activity"

    For example:
    - "Get all activities" -> get all activities
    - "Show details for activity 25" -> get activity by id, 25
    - "Create an activity for deal 2" -> create activity, deal_id=2
    - "Create activity titled Presentation" -> create activity, subject=Presentation
    - "Update activity 52" -> update activity, 52
    - "Delete activity 30" -> delete activity, 30

    User query: "{user_query}"

    Method and parameters:
    """

    llm = ChatGroq(model="llama3-70b-8192", temperature=0.2, groq_api_key=api_key)

    chain = LLMChain(
        prompt=ChatPromptTemplate.from_template(template=prompt_template),
        llm=llm,
        output_parser=StrOutputParser()
    )

    llm_response = chain.run(user_query)

    method_name, params = parse_llm_response(llm_response)
    st.write("Method name and parameters : ",method_name,params)

    if method_name == "create activity":
        activity_details = {}
        if params:
            for key, value in params.items():
                activity_details[key] = value

        response = create_activity(activity_details)
        st.write(json.dumps(response, indent=4))

    elif method_name == "update activity":
        activity_id = params.pop('id', None)
        if activity_id:
            response = update_activity(activity_id, params)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Activity ID is required for updating an activity.")

    elif method_name == "delete activity":
        activity_id = params.get('id')
        if activity_id:
            response = delete_activity(activity_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Activity ID is required for deleting an activity.")

    elif method_name == "get activity by id":
        activity_id = params.get('id')
        if activity_id:
            response = get_activity_by_id(activity_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Activity ID is required for retrieving activity details.")

    elif method_name == "get all activities":
        response = get_all_activities()
        st.write(json.dumps(response, indent=4))

    else:
        st.write("Method not recognized.")


# # **STAGES**



def ask_for_missing_details(update_data=None):
    if update_data is None:
        update_data = {}

    st.write("Select options to modify details:")
    st.write("1. Name")
    st.write("2. Pipeline ID")
    st.write("3. Enable Deal Rot Option")
    st.write("If you do not want to update anything, enter none")
    st.write("Enter numbers separated by commas (e.g., 1,3): ")
    selected_options = st.text_input().strip().lower().split(',')

    selected_options = [opt.strip() for opt in selected_options if opt.strip()]

    if '1' in selected_options:
        st.write("Enter the new name for the stage: ")
        update_data['name'] = st.text_input().strip()

    if '2' in selected_options:
        st.write("Enter the new pipeline ID for the stage: ")
        update_data['pipeline_id'] = st.text_input().strip()

    if '3' in selected_options:
        st.write("Enable deal rot? (yes/no): ")
        response = st.text_input().strip().lower()
        update_data['rotten_flag'] = True if response == 'yes' else False

        if update_data.get('rotten_flag'):
            st.write("Enter the number of days to rotten: ")
            rotten_days_input = st.text_input().strip()
            update_data['rotten_days'] = int(rotten_days_input) if rotten_days_input.isdigit() else None

    return update_data

def ask_for_additional_create_details(data):
    st.write("Would you like to set additional details for the new stage?")
    st.write("1. Enable Deal Rot Option")
    st.write("If you do not want to set any additional details, enter none")
    user_input = st.text_input('Enter your input:', value='').strip().lower()
    selected_options = [opt.strip() for opt in user_input.split(',')]

    if '1' in selected_options:
        st.write("Enable deal rot? (yes/no): ")
        response = st.text_input().strip().lower()
        data['rotten_flag'] = True if response == 'yes' else False

        if data.get('rotten_flag'):
            st.write("Enter the number of days to rotten: ")
            data['rotten_days'] = st.text_input().strip()
            data['rotten_days'] = int(data['rotten_days']) if data['rotten_days'].isdigit() else None

    return data

def get_all_stages():
    url = f'https://api.pipedrive.com/v1/stages?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def get_stage_by_id(stage_id):
    url = f'https://api.pipedrive.com/v1/stages/{stage_id}?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def get_deals_in_stage(stage_id):
    url = f'https://api.pipedrive.com/v1/stages/{stage_id}/deals?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def add_new_stage(name, pipeline_id,new_values=None):

    url = f'https://api.pipedrive.com/v1/stages?api_token={api_token}'
    data = {
        "name": name,
        "pipeline_id": pipeline_id
    }

    if not new_values:
        data = ask_for_additional_create_details(data)
        st.write("Data being sent to API:", json.dumps(data, indent=4))
        response = requests.post(url, json=data)
        return response.json()

    if 'rotten_flag' in new_values:
        rotten_flag_str = new_values['rotten_flag'].lower().strip()
        if rotten_flag_str == 'true':
            new_values['rotten_flag'] = True
        elif rotten_flag_str == 'false':
            new_values['rotten_flag'] = False
            new_values['rotten_days'] = "0"
    st.write("Data being sent to API:", json.dumps(new_values, indent=4))
    response = requests.post(url, json=new_values)
    return response.json()

def update_stage(stage_id, update_data=None):
    if update_data is None:
        update_data = {}

    if not update_data:
        update_data = ask_for_missing_details()

    if 'rotten_flag' in update_data:
        rotten_flag_str = update_data['rotten_flag'].lower().strip()
        if rotten_flag_str == 'true':
            update_data['rotten_flag'] = True
        elif rotten_flag_str == 'false':
            update_data['rotten_flag'] = False
            update_data['rotten_days'] = "0"

    st.write("Data being sent to API:", json.dumps(update_data, indent=4))


    url = f'https://api.pipedrive.com/v1/stages/{stage_id}?api_token={api_token}'
    response = requests.put(url, json=update_data)
    return response.json()

def delete_stage(stage_id):
    url = f'https://api.pipedrive.com/v1/stages/{stage_id}?api_token={api_token}'
    response = requests.delete(url)
    return response.json()

def handle_stage_query(user_query):
    prompt_template = """
    You are an AI assistant for Pipedrive API interactions. Based on the user's input, return the exact method name and relevant parameters as a comma-separated list. Only use these method names:
    -"get all stages"
    -"get stage by id"
    -"get deals in stage"
    -"add new stage"
    -"update stage"
    -"delete stage"

    Exceptions:
    -"Update stage 27, set rotten flag as True and keep rotten days as 16" -> update stage, id=27, rotten_flag=true, rotten_days=16
    -"Update stage 27, disable rotten flag and keep rotten days as 16" -> update stage, id=27, rotten_flag=false, rotten_days=0

    Examples:
    -"Get all stages" -> get all stages
    -"Show details for stage 25" -> get stage by id, 25
    -"Get deals in stage 23" -> get deals in stage, 23
    -"Add a new stage Final Review for pipeline 2" -> add new stage, name=Final Review, pipeline_id=2
    -"Update stage 52" -> update stage, 52
    -"Delete stage 30" -> delete stage, 30

    User query: "{user_query}"
    Method and parameters:
    """

    llm = ChatGroq(model="llama3-70b-8192", temperature=0.2, groq_api_key=api_key)

    chain = LLMChain(
        prompt=ChatPromptTemplate.from_template(template=prompt_template),
        llm=llm,
        output_parser=StrOutputParser()
    )

    llm_response = chain.run(user_query)

    method_name, params = parse_llm_response(llm_response)
    st.write("Method name and parameters : ",method_name,params)

    if method_name == "add new stage":
        name = params.get('name')
        pipeline_id = params.get('pipeline_id')
        if name and pipeline_id:
            response = add_new_stage(name, pipeline_id,params)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Name and pipeline ID are required for adding a new stage.")

    elif method_name == "update stage":
        stage_id = params.pop('id', None)
        if stage_id:
            response = update_stage(stage_id, params)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Stage ID is required for updating a stage.")


    elif method_name == "delete stage":
        stage_id = params.get('id')
        if stage_id:
            response = delete_stage(stage_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Stage ID is required for deleting a stage.")

    elif method_name == "get stage by id":
        stage_id = params.get('id')
        if stage_id:
            response = get_stage_by_id(stage_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Stage ID is required for retrieving stage details.")

    elif method_name == "get all stages":
        response = get_all_stages()
        st.write(json.dumps(response, indent=4))

    elif method_name == "get deals in stage":
        stage_id = params.get('id')
        if stage_id:
            response = get_deals_in_stage(stage_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Stage ID is required for retrieving deals in stage.")

    else:
        st.write("Method not recognized.")


# # **DEALS**



def get_all_deals():
    url = f'https://api.pipedrive.com/v1/deals?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def search_deals(term):
    url = f'https://api.pipedrive.com/v1/deals/search?api_token={api_token}&term={term}'
    response = requests.get(url)
    return response.json()

def get_deals_summary():
    url = f'https://api.pipedrive.com/v1/deals/summary?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def get_deals_timeline(start_date, interval, amount, field_key):
    url = f'https://api.pipedrive.com/v1/deals/timeline?api_token={api_token}'
    params = {
        'start_date': start_date,
        'interval': interval,
        'amount': amount,
        'field_key': field_key
    }

    st.write("Data being sent to API:", json.dumps(params, indent=4))
    response = requests.get(url, params=params)
    return response.json()

def get_deal_details(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_activities_associated_with_a_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/activities?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_updates_about_a_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/flow?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_files_attached_to_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/files?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_mail_messages_associated_with_a_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/mailMessages?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_all_participants_associated_with_a_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/participants?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_all_persons_associated_with_a_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/persons?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_products_attached_to_a_deal(deal_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/products?api_token={api_token}'
    response = requests.get(url)
    return response.json()


# ADD/UPDATE METHODS

# add a deal
def ask_for_deal_additional_details(data):
    st.write("Would you like to set additional details?")
    st.write("1. Person ID")
    st.write("2. Organization ID")
    st.write("3. Stage ID")
    st.write("4. Value")
    st.write("5. Currency")
    st.write("If you do not want to set any additional details, enter 'none'")

    user_input = st.text_input('Enter your input:', value='').strip().lower()
    selected_options = [opt.strip() for opt in user_input.split(',')]

    if '1' in selected_options:
        st.write("Enter Person ID: ")
        person_id = st.text_input().strip()
        data['person_id'] = int(person_id) if person_id.isdigit() else None

    if '2' in selected_options:
        st.write("Enter Organization ID: ")
        org_id = st.text_input().strip()
        data['org_id'] = int(org_id) if org_id.isdigit() else None

    if '3' in selected_options:
        st.write("Enter Stage ID: ")
        stage_id = st.text_input().strip()
        data['stage_id'] = int(stage_id) if stage_id.isdigit() else None

    if '4' in selected_options:
        st.write("Enter Value: ")
        value = st.text_input().strip()
        data['value'] = float(value) if value.replace('.', '', 1).isdigit() else None

    if '5' in selected_options:
        st.write("Enter Currency: ")
        currency = st.text_input().strip()
        data['currency'] = currency

    return data


def add_a_deal(title, new_values=None):
    if new_values is None:
        new_values = {}
    if new_values:
        new_values['title'] = title
        if 'currency' in new_values:
            new_values['currency'] = new_values['currency'].upper()
        url = f'https://api.pipedrive.com/v1/deals?api_token={api_token}'
        st.write("Data being sent to API:", json.dumps(new_values, indent=4))
        response = requests.post(url, json=new_values)
        return response.json()
    else:
        data = {'title': title,}
        new_values = ask_for_deal_additional_details(data)
        url = f'https://api.pipedrive.com/v1/deals?api_token={api_token}'
        st.write("Data being sent to API:", json.dumps(new_values, indent=4))
        response = requests.post(url, json=new_values)
        return response.json()


# add participant to deal
def add_participant_to_deal(deal_id, person_id):
    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/participants?api_token={api_token}'
    data = {
        'person_id': person_id
        }

    response = requests.post(url, json=data)
    return response.json()

# add product to deal
def ask_for_product_additional_details(data):
    st.write("Would you like to set additional details?")
    st.write("1.Set Tax")
    st.write("2.Set Discount ")
    st.write("If you do not want to set any additional details, enter 'none'")

    user_input = st.text_input('Enter your input:', value='').strip().lower()
    selected_options = [opt.strip() for opt in user_input.split(',')]

    if '1' in selected_options:
        st.write("Enter tax amount: ")
        tax = st.text_input().strip()
        data['tax'] = float(tax) if tax.replace('.', '', 1).isdigit() else 0.0

    if '2' in selected_options:
        st.write("Enter discount type (percentage/amount): ")
        discount_type = st.text_input().strip().lower()
        if discount_type in ['percentage', 'amount']:
            data['discount_type'] = discount_type
            if discount_type == 'percentage':
                while True:
                    st.write("Enter discount percentage (0-100): ")
                    discount = st.text_input().strip()
                    if discount.isdigit() and 0 <= int(discount) <= 100:
                        data['discount'] = int(discount)
                        break
                    else:
                        st.write("Invalid input. Please enter a number between 0 and 100.")
            elif discount_type == 'amount':
                while True:
                    st.write("Enter discount amount: ")
                    discount = st.text_input().strip()
                    if discount.isdigit():
                        data['discount'] = int(discount)
                        break
                    else:
                        st.write("Invalid input. Please enter a valid number.")
    return data

def add_product_to_deal(deal_id, product_id, item_price, quantity):
    deal_id = int(deal_id)
    product_id = int(product_id)
    quantity = int(quantity)
    item_price = float(item_price)

    url = f'https://api.pipedrive.com/v1/deals/{deal_id}/products?api_token={api_token}'
    data = {
        'product_id': product_id,
        'item_price': item_price,
        'quantity': quantity,
    }

    data = ask_for_product_additional_details(data)

    st.write("Data being sent to API:", json.dumps(data, indent=4))
    response = requests.post(url, json=data)
    return response.json()

# update a deal
def ask_for_deal_update_details(deal_details):
    st.write("Select options to add/modify details:")
    st.write("1. Person ID")
    st.write("2. Organization ID")
    st.write("3. Stage ID")
    st.write("4. Value")
    st.write("5. Currency")
    st.write("If you do not want to add/modify anything, enter 'none'")
    st.write("Enter numbers separated by commas (e.g., 1,3,5): ")
    user_input = st.text_input('Enter your input:', value='').strip().lower()

    if user_input == "none":
        return deal_details

    selected_options = [opt.strip() for opt in user_input.split(',')]
    field_options = {
        '1': 'person_id',
        '2': 'org_id',
        '3': 'stage_id',
        '4': 'value',
        '5': 'currency'
    }

    prompts = {
        'person_id': "Please provide the person ID associated with this deal.",
        'org_id': "Please provide the organization ID associated with this deal.",
        'stage_id': "Please provide the stage ID for the deal.",
        'value': "Please provide the value of the deal.",
        'currency': "Please specify the currency of the deal."
    }

    for option in selected_options:
        field = field_options.get(option)
        if field:
            st.write(prompts[field])
            input_value = st.text_input().strip()

            if field == 'value':
                deal_details[field] = float(input_value) if input_value.replace('.', '', 1).isdigit() else None
            elif field == 'currency':
                deal_details[field] = input_value.upper()
            else:
                deal_details[field] = int(input_value) if input_value.isdigit() else input_value

    return deal_details




def update_a_deal(deal_id, new_values=None):
    if new_values is None:
        new_values = {}
    if new_values:
      if 'currency' in new_values:
        new_values['currency'] = new_values['currency'].upper()
      url = f'https://api.pipedrive.com/v1/deals/{deal_id}?api_token={api_token}'
      st.write("Data being sent to API:", json.dumps(new_values, indent=4))
      response = requests.put(url, json=new_values)
      return response.json()
    else:
        deal_details = get_deal_details(deal_id)
        new_values = ask_for_deal_update_details(deal_details)

        url = f'https://api.pipedrive.com/v1/deals/{deal_id}?api_token={api_token}'
        st.write("Data being sent to API:", json.dumps(new_values, indent=4))
        response = requests.put(url, json=new_values)
        return response.json()


# update product of deal
def ask_for_deal_product_update_details(product_details):
    st.write("Select options to add/modify product details:")
    st.write("1. Product ID")
    st.write("2. Item Price")
    st.write("3. Quantity")
    st.write("4. Discount")
    st.write("5. Tax")
    st.write("If you do not want to add/modify anything, enter 'none'")
    st.write("Enter numbers separated by commas (e.g., 1,3,5): ")

    user_input = st.text_input('Enter your input:', value='').strip().lower()

    if user_input == "none":
        return product_details

    selected_options = [opt.strip() for opt in user_input.split(',')]
    field_options = {
        '1': 'product_id',
        '2': 'item_price',
        '3': 'quantity',
        '4': 'discount',
        '5': 'tax'
    }

    prompts = {
        'product_id': "Please provide the new product ID.",
        'item_price': "Please provide the new item price.",
        'quantity': "Please provide the new quantity.",
        'discount': "Please provide the new discount.",
        'tax': "Please provide the new tax."
    }

    for option in selected_options:
        field = field_options.get(option)
        if field:
            st.write(prompts[field])
            input_value = st.text_input().strip()

            if field in ['item_price', 'quantity', 'tax']:
                product_details[field] = float(input_value) if input_value.replace('.', '', 1).isdigit() else None
            elif field == 'discount':
                product_details[field] = input_value
            else:
                product_details[field] = int(input_value) if input_value.isdigit() else input_value

    return product_details

def update_product_attached_to_deal(deal_id, product_attachment_id, new_values=None):
    if new_values is None:
        new_values = {}

    if new_values:
        url = f'https://api.pipedrive.com/v1/deals/{deal_id}/products/{product_attachment_id}?api_token={api_token}'
        st.write("Data being sent to API:", json.dumps(new_values, indent=4))
        response = requests.put(url, json=new_values)
        return response.json()
    else:
        data = ask_for_deal_product_update_details({})

        url = f'https://api.pipedrive.com/v1/deals/{deal_id}/products/{product_attachment_id}?api_token={api_token}'
        st.write("Data being sent to API:", json.dumps(data, indent=4))
        response = requests.put(url, json=data)
        return response.json()

# DELETE METHODS

# delete deal
def delete_deal(deal_id):
    url=  f'https://api.pipedrive.com/v1/deals/{deal_id}?api_token={api_token}'
    response = requests.delete(url)
    return response.json()

#delete pariticipant
def delete_participant_from_deal(deal_id, participant_id):
    url=  f'https://api.pipedrive.com/v1/deals/{deal_id}/participants/{participant_id}?api_token={api_token}'
    response = requests.delete(url)
    return response.json()

#delete product
def delete_product_from_deal(deal_id, product_attachment_id):
    url=  f'https://api.pipedrive.com/v1/deals/{deal_id}/products/{product_attachment_id}?api_token={api_token}'
    response = requests.delete(url)
    return response.json()


def parse_deal_llm_response(llm_response):
    llm_response = llm_response.strip().lower()
    parts = map(str.strip, llm_response.split(","))

    method_name = next(parts, "").strip()
    params = {}

    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip()] = value.strip()
        elif part.isdigit():
            params['deal_id'] = part
        elif part:
            params['term'] = part

    return method_name, params

def handle_deal_query(user_query):
  prompt_template = """
  You are an AI assistant for interacting with the Pipedrive API. Based on the user's query, return the exact method name and any relevant parameters as a comma-separated list. Be precise with the method name you provide. You must use ONLY the following method names:
  - "get all deals"
  - "search deals"
  - "get deals summary"
  - "get deals timeline"
  - "get deal details"
  - "list activities associated with a deal"
  - "list updates about a deal"
  - "list files attached to a deal"
  - "list mail messages associated with a deal"
  - "list all participants associated with a deal"
  - "list all persons associated with a deal"
  - "list products attached to a deal"
  - "add a deal"
  - "add participant to deal"
  - "add product to deal"
  - "update a deal"
  - "update product attached to deal"
  - "delete deal"
  - "delete participant from deal"
  - "delete product from deal"
  - "no method"

  Examples:
  - "Show all deals" -> get all deals
  - "Search for deals with term 'Acme'" -> search deals, term=Acme
  - "Get summary of all deals" -> get deals summary
  - "Get deals timeline from 2024-01-01 with interval 30 days, amount 5, and field_key 'close_date'" -> get deals timeline, start_date=2024-01-01, interval=30 days, amount=5, field_key=close_date
  - "Get details for deal 12" -> get deal details, id=12
  - "List activities associated with deal 34" -> list activities associated with a deal, id=34
  - "List updates about deal 34" -> list updates about a deal, id=34
  - "List files attached to deal 34" -> list files attached to a deal, id=34
  - "List mail messages associated with deal 34" -> list mail messages associated with a deal, id=34
  - "List all participants associated with deal 34" -> list all participants associated with a deal, id=34
  - "List all persons associated with deal 34" -> list all persons associated with a deal, id=34
  - "List products attached to deal 34" -> list products attached to a deal, id=34
  - "Add a new deal titled 'New Opportunity'" -> add a deal, title=New Opportunity
  - "Add participant with ID 5 to deal 34" -> add participant to deal, deal_id=34, person_id=5
  - "Add product with ID 2 to deal 34, priced at 100.0 with quantity 10" -> add product to deal, deal_id=34, product_id=2, item_price=100.0, quantity=10
  - "update deal 19 , value 9000" -> update a deal, deal_id=34, value=9000
  - "Update product 2 in deal 34" -> update product attached to deal, deal_id=34, product_attachment_id=2
  - "Delete deal 56" -> delete deal, id=56
  - "Delete participant with ID 5 from deal 34" -> delete participant from deal, deal_id=34, participant_id=5
  - "Delete product with ID 2 from deal 34" -> delete product from deal, deal_id=34, product_attachment_id=2
  - "Please produce a detailed timeline for our deals, starting from January 1st, 2024, broken down into daily segments and emphasizing the dates on which they were won, covering the subsequent five intervals." -> get deals timeline, start_date=2024-01-01, interval=day, amount=5, field_key=won_time
  User query: "{user_query}"

  Method and parameters:
  """

  llm = ChatGroq(model="llama3-70b-8192", temperature=0, groq_api_key=api_key)

  chain = LLMChain(
        prompt=ChatPromptTemplate.from_template(template=prompt_template),
        llm=llm,
        output_parser=StrOutputParser()
  )

  llm_response = chain.run(user_query)

  method_name, params = parse_deal_llm_response(llm_response)
  st.write("Method name and parameters : ",method_name,params)

  if method_name == "get all deals":
    response = get_all_deals()
    st.write(json.dumps(response, indent=4))

  elif method_name == "search deals":
    term = params.get('term')
    if term:
      response = search_deals(term)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Search term is required to search deals.")

  elif method_name == "get deals summary":
    response = get_deals_summary()
    st.write(json.dumps(response, indent=4))

  elif method_name == "get deals timeline":
    start_date = params.get('start_date')
    interval = params.get('interval')
    amount = params.get('amount')
    field_key = params.get('field_key')
    if start_date and interval and amount and field_key:
      response = get_deals_timeline(start_date, interval, amount, field_key)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("All parameters (start_date, interval, amount, field_key) are required to get the deals timeline.")

  elif method_name == "get deal details":
    deal_id = params.get('id')
    if deal_id:
      response = get_deal_details(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required for retrieving deal details.")

  elif method_name == "list activities associated with a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_activities_associated_with_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list activities.")

  elif method_name == "list updates about a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_updates_about_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list updates.")

  elif method_name == "list files attached to a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_files_attached_to_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list files.")

  elif method_name == "list mail messages associated with a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_mail_messages_associated_with_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list mail messages.")

  elif method_name == "list all participants associated with a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_all_participants_associated_with_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list participants.")

  elif method_name == "list all persons associated with a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_all_persons_associated_with_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list persons.")

  elif method_name == "list products attached to a deal":
    deal_id = params.get('id')
    if deal_id:
      response = list_products_attached_to_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to list products.")

  elif method_name == "add a deal":
    title = params.get('title')
    if title:
      fields_to_update = {key: value for key, value in params.items() if key != 'title'}

      if fields_to_update:
        response = add_a_deal(title, fields_to_update)
        st.write(json.dumps(response, indent=4))
      else:
        response = add_a_deal(title)
        st.write(json.dumps(response, indent=4))
    else:
      st.write("Title is required to add a deal.")

  elif method_name == "add participant to deal":
    deal_id = params.get('deal_id')
    person_id = params.get('person_id')
    if deal_id and person_id:
      response = add_participant_to_deal(deal_id, person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Both deal_id and person_id are required to add a participant.")

  elif method_name == "add product to deal":
    deal_id = params.get('deal_id')
    product_id = params.get('product_id')
    item_price = params.get('item_price')
    quantity = params.get('quantity')
    if deal_id and product_id and item_price and quantity:
      response = add_product_to_deal(deal_id, product_id, item_price, quantity)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID, Product ID, Item Price, and Quantity are required to add a product.")

  elif method_name == "update a deal":
    deal_id = params.get('deal_id')
    if deal_id:

      fields_to_update = {key: value for key, value in params.items() if key != 'deal_id'}

      if fields_to_update:
        response = update_a_deal(deal_id, fields_to_update)
        st.write(json.dumps(response, indent=4))
      else:
        response = update_a_deal(deal_id)
        st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to update a deal.")

  elif method_name == "update product attached to deal":
    deal_id = params.get('deal_id')
    product_attachment_id = params.get('product_attachment_id')
    if deal_id and product_attachment_id:
        if 'item_price' in params:
            params['item_price'] = float(params['item_price'])
        if 'quantity' in params:
            params['quantity'] = int(params['quantity'])

        fields_to_update = {key: value for key, value in params.items() if key != 'deal_id' and key != 'product_attachment_id'}
        if fields_to_update:
            response = update_product_attached_to_deal(deal_id, product_attachment_id, fields_to_update)
            st.write(json.dumps(response, indent=4))
        else:
            response = update_product_attached_to_deal(deal_id, product_attachment_id)
            st.write(json.dumps(response, indent=4))
    else:
        st.write("Both deal_id and product_attachment_id are required to update a product attached to a deal.")


  elif method_name == "delete deal":
    deal_id = params.get('id')
    if deal_id:
      response = delete_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required to delete a deal.")

  elif method_name == "delete participant from deal":
    deal_id = params.get('deal_id')
    participant_id = params.get('participant_id')
    if deal_id and participant_id:
      response = delete_participant_from_deal(deal_id, participant_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Both deal_id and participant_id are required to delete a participant from a deal.")

  elif method_name == "delete product from deal":
    deal_id = params.get('deal_id')
    product_attachment_id = params.get('product_attachment_id')
    if deal_id and product_attachment_id:
      response = delete_product_from_deal(deal_id, product_attachment_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Both deal_id and product_attachment_id are required to delete a product from a deal.")

  else:
    st.write("Method not recognized.")


# # **PERSONS**


def ask_for_additional_person_details(data):
    st.write("Would you like to set additional details for the new person?")
    st.write("1. Email")
    st.write("2. Phone")
    st.write("3. Organization ID")
    st.write("If you do not want to set any additional details, enter 'none'")
    user_input = st.text_input('Enter your input:', value='').strip().lower()
    selected_options = [opt.strip() for opt in user_input.split(',')]

    if '1' in selected_options:
        data['email'] = st.text_input("Enter the email: ").strip()

    if '2' in selected_options:
        data['phone'] = st.text_input("Enter the phone number: ").strip()

    if '3' in selected_options:
        data['org_id'] = st.text_input("Enter the organization ID: ").strip()

    return data

# Ask for missing details when updating a person
def ask_for_missing_person_details(update_data=None):
    if update_data is None:
        update_data = {}

    st.write("Select options to modify details:")
    st.write("1. Name")
    st.write("2. Email")
    st.write("3. Phone")
    st.write("4. Organization ID")
    st.write("If you do not want to update anything, enter 'none'")
    st.write("Enter numbers separated by commas (e.g., 1,3): ")
    selected_options = st.text_input().strip().lower().split(',')

    selected_options = [opt.strip() for opt in selected_options if opt.strip()]

    if '1' in selected_options:
        update_data['name'] = st.text_input("Enter the new name for the person: ").strip()

    if '2' in selected_options:
        update_data['email'] = st.text_input("Enter the new email for the person: ").strip()

    if '3' in selected_options:
        update_data['phone'] = st.text_input("Enter the new phone number for the person: ").strip()

    if '4' in selected_options:
        update_data['org_id'] = st.text_input("Enter the new organization ID for the person: ").strip()

    return update_data

def add_person(name, email=None, phone=None, org_id=None):
    url = f'https://api.pipedrive.com/v1/persons?api_token={api_token}'
    data = {
        "name": name
    }

    if email:
        data['email'] = email

    if phone:
        data['phone'] = phone

    if org_id:
        data['org_id'] = org_id

    # Only ask for additional details if they were not provided
    if not (email or phone or org_id):
        data = ask_for_additional_person_details(data)

    st.write("Data being sent to API:", json.dumps(data, indent=4))
    response = requests.post(url, json=data)
    return response.json()

# Update an existing person
def update_person(person_id=None, new_values=None):
    if new_values is None:
        new_values = {}

    if person_id is None:
        st.write("Person ID is required for updating a person.")
        person_id = st.text_input("Enter the person ID: ").strip()

    url = f'https://api.pipedrive.com/v1/persons/{person_id}?api_token={api_token}'

    update_data = {key: new_values[key] for key in new_values if key in ['name', 'email', 'phone', 'org_id']}

    if update_data:
        # Update with specified fields
        st.write("Data being sent to API:", json.dumps(update_data, indent=4))
        response = requests.put(url, json=update_data)
    else:
        # If no fields are specified, prompt the user
        update_data = ask_for_missing_person_details()
        if update_data:  # Only if there's data to update
            st.write("Data being sent to API:", json.dumps(update_data, indent=4))
            response = requests.put(url, json=update_data)
        else:
            st.write("No details were provided for updating.")
            response = {"error": "No details provided for update"}

    return response.json()

# Delete an existing person
def delete_person(person_id):
    if person_id is None:
        st.write("Person ID is required for deleting a person.")
        person_id = st.text_input("Enter the person ID: ").strip()

    url = f'https://api.pipedrive.com/v1/persons/{person_id}?api_token={api_token}'

    st.write(f"Deleting person with ID: {person_id}")
    response = requests.delete(url)
    return response.json()

# Get all persons
def get_all_persons():
    url = f'https://api.pipedrive.com/v1/persons?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# Search persons by term
def search_persons(term):
    url = f'https://api.pipedrive.com/v1/persons/search?term={term}&api_token={api_token}'
    response = requests.get(url)
    return response.json()

# Get a person by ID
def get_person_by_id(person_id):
    url = f'https://api.pipedrive.com/v1/persons/{person_id}?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# List activities for a person
def list_person_activities(person_id):
    url = f'https://api.pipedrive.com/v1/persons/{person_id}/activities?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# List updates for a person
def list_person_updates(person_id):
    url = f'https://api.pipedrive.com/v1/persons/{person_id}/flow?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# List deals for a person
def list_person_deals(person_id):
    url = f'https://api.pipedrive.com/v1/persons/{person_id}/deals?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# List files for a person
def list_person_files(person_id):
    url = f'https://api.pipedrive.com/v1/persons/{person_id}/files?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# List products for a person
def list_person_products(person_id):
    url = f'https://api.pipedrive.com/v1/persons/{person_id}/products?api_token={api_token}'
    response = requests.get(url)
    return response.json()


def handle_person_query(user_query):
  prompt_template = """
  You are an AI assistant for interacting with the Pipedrive API. Based on the user's query, return the exact method name and any relevant parameters as a comma-separated list. Only use the following method names:
  - "add person"
  - "update person"
  - "delete person"
  - "get all persons"
  - "search persons"
  - "get person by id"
  - "list person activities"
  - "list person updates"
  - "list person deals"
  - "list person files"
  - "list person products"
  - "list all persons associated with a deal"

  For example:
  - "Add a person named 'John Doe'" -> add person, name=John Doe
  - "Update the person with ID 5, changing their name to Jane Doe and email to jane.doe@example.com" -> update person, id=5, name=Jane Doe, email=jane.doe@example.com
  - "Update person 1, with organization id as 8" -> update person, id=1, org_id=8
  - "Delete the person with ID 3" -> delete person, id=3
  - "Show all persons" -> get all persons
  - "Search for persons with the name John" -> search persons, term=John
  - "Get details for person 12" -> get person by id, id=12
  - "List activities for person 15" -> list person activities, id=15
  - "Show updates for person 20" -> list person updates, id=20
  - "List deals associated with person 25" -> list person deals, id=25
  - "List all persons associated with deal 34" -> list all persons associated with a deal, deal_id=34
  - "List files for person 30" -> list person files, id=30
  - "List products associated with person 40" -> list person products, id=40


  User query: "{user_query}"

  Method and parameters:
  """

  llm = ChatGroq(model="llama3-70b-8192", temperature=0.2, groq_api_key=api_key)

  chain = LLMChain(
  prompt=ChatPromptTemplate.from_template(template=prompt_template),
  llm=llm,
  output_parser=StrOutputParser()
  )

  llm_response = chain.run(user_query)

  method_name, params = parse_llm_response(llm_response)
  st.write("Method name and parameters : ",method_name,params)

  if method_name == "add person":
    name = params.get('name')
    if not name or not name.strip():
      name = st.text_input("Name is required. Please enter the name: ").strip()

    email = params.get('email')
    phone = params.get('phone')
    org_id = params.get('org_id')

    response = add_person(name, email=email, phone=phone, org_id=org_id)
    st.write(json.dumps(response, indent=4))

  elif method_name == "update person":
    person_id = params.get('id')
    if not person_id:
      person_id = st.text_input("Person ID is required. Please enter the person ID: ").strip()

    fields_to_update = {key: value for key, value in params.items() if key != 'id'}
    response = update_person(person_id, fields_to_update)
    st.write(json.dumps(response, indent=4))

  elif method_name == "delete person":
    person_id = params.get('id')
    response = delete_person(person_id)
    st.write(json.dumps(response, indent=4))

  elif method_name == "get all persons":
    response = get_all_persons()
    st.write(json.dumps(response, indent=4))

  elif method_name == "search persons":
    term = params.get('term')
    if term:
      response = search_persons(term)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Search term is required.")

  elif method_name == "get person by id":
    person_id = params.get('id')
    if person_id:
      response = get_person_by_id(person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Person ID is required for retrieving details.")

  elif method_name == "list person activities":
    person_id = params.get('id')
    if person_id:
      response = list_person_activities(person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Person ID is required for listing activities.")

  elif method_name == "list person updates":
    person_id = params.get('id')
    if person_id:
      response = list_person_updates(person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Person ID is required for listing updates.")

  elif method_name == "list person deals":
    person_id = params.get('id')
    if person_id:
      response = list_person_deals(person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Person ID is required for listing deals.")

  elif method_name == "list person files":
    person_id = params.get('id')
    if person_id:
      response = list_person_files(person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Person ID is required for listing files.")

  elif method_name == "list person products":
    person_id = params.get('id')
    if person_id:
      response = list_person_products(person_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Person ID is required for listing products.")



  elif method_name == "list all persons associated with a deal":
    deal_id = params.get('deal_id')
    if deal_id:
      response = list_all_persons_associated_with_a_deal(deal_id)
      st.write(json.dumps(response, indent=4))
    else:
      st.write("Deal ID is required for listing products.")

  else:
    st.write(f"Method '{method_name}' not recognized.")


# # **ORGANIZATIONS**


def get_all_organizations():
    url = f'https://api.pipedrive.com/v1/organizations?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def search_organizations(term):
    url = f'https://api.pipedrive.com/v1/organizations/search?term={term}&api_token={api_token}'
    response = requests.get(url)
    return response.json()

def get_organization_by_id(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_organization_activities(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}/activities?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_organization_updates(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}/flow?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_organization_deals(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}/deals?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_organization_files(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}/files?api_token={api_token}'
    response = requests.get(url)
    return response.json()

def list_persons_of_organization(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}/persons?api_token={api_token}'
    response = requests.get(url)
    return response.json()

# Add, update, and delete functions
def add_organization(name):
    url = f'https://api.pipedrive.com/v1/organizations?api_token={api_token}'
    data = {'name': name}
    response = requests.post(url, json=data)
    return response.json()

def update_organization(org_id=None, new_name=None):
    if org_id is None:
        st.write("Organization ID is required for updating an organization.")
        org_id = st.text_input("Enter the organization ID: ").strip()

    if new_name is None:
        new_name = st.text_input("Enter the new name for the organization: ").strip()

    url = f'https://api.pipedrive.com/v1/organizations/{org_id}?api_token={api_token}'
    update_data = {"name": new_name}
    response = requests.put(url, json=update_data)
    return response.json()

def delete_organization(org_id):
    url = f'https://api.pipedrive.com/v1/organizations/{org_id}?api_token={api_token}'
    response = requests.delete(url)
    return response.json()

def handle_organization_query(user_query):
    # The prompt template for LLM
    prompt_template = """
    You are an AI assistant for interacting with the Pipedrive API. Based on the user's query, return the exact method name and any relevant parameters as a comma-separated list. Only use the following method names:
    - "get all organizations"
    - "search organizations"
    - "get organization by id"
    - "list organization activities"
    - "list organization updates"
    - "list organization deals"
    - "list organization files"
    - "list persons of organization"
    - "add organization"
    - "update organization"
    - "delete organization"

    For example:
    - "Show all organizations" -> get all organizations
    - "Search for organizations with the name ABC Corp" -> search organizations, term=ABC Corp
    - "Get details for organization 12" -> get organization by id, 12
    - "List activities for organization 15" -> list organization activities, 15
    - "Show updates for organization 20" -> list organization updates, 20
    - "List deals associated with organization 25" -> list organization deals, 25
    - "List files for organization 30" -> list organization files, 30
    - "List persons of organization 40" -> list persons of organization, 40
    - "Create an organization named TechCorp" -> add organization, name=TechCorp
    - "Update the organization with ID 10, changing its name to Tech Innovators" -> update organization, id=10, name=Tech Innovators
    - "Delete organization with ID 50" -> delete organization, id=50

    User query: "{user_query}"

    Method and parameters:
    """

    prompt = ChatPromptTemplate.from_template(template=prompt_template)
    llm = ChatGroq(model="llama3-70b-8192", temperature=0.2, groq_api_key="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")

    chain = LLMChain(
        prompt=prompt,
        llm=llm,
        output_parser=StrOutputParser()
    )

    llm_response = chain.run(user_query)
    method_name, params = parse_llm_response(llm_response)
    st.write("Method name and parameters : ",method_name,params)

    if method_name == "get all organizations":
        response = get_all_organizations()
        st.write(json.dumps(response, indent=4))

    elif method_name == "search organizations":
        term = params.get('term')
        if term:
            response = search_organizations(term)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Search term is required.")

    elif method_name == "get organization by id":
        org_id = params.get('id')
        if org_id:
            response = get_organization_by_id(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for retrieving details.")

    elif method_name == "list organization activities":
        org_id = params.get('id')
        if org_id:
            response = list_organization_activities(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for listing activities.")

    elif method_name == "list organization updates":
        org_id = params.get('id')
        if org_id:
            response = list_organization_updates(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for listing updates.")

    elif method_name == "list organization deals":
        org_id = params.get('id')
        if org_id:
            response = list_organization_deals(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for listing deals.")

    elif method_name == "list organization files":
        org_id = params.get('id')
        if org_id:
            response = list_organization_files(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for listing files.")

    elif method_name == "list persons of organization":
        org_id = params.get('id')
        if org_id:
            response = list_persons_of_organization(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for listing persons.")

    elif method_name == "add organization":
        name = params.get('name')
        while not name:
            st.write("Name is required to add a new organization.")
            name = st.text_input("Please enter the organization's name: ").strip()
        response = add_organization(name=name)
        st.write(json.dumps(response, indent=4))

    elif method_name == "update organization":
        org_id = params.get('id')
        new_name = params.get('name')
        response = update_organization(org_id, new_name)
        st.write(json.dumps(response, indent=4))

    elif method_name == "delete organization":
        org_id = params.get('id')
        if org_id:
            response = delete_organization(org_id)
            st.write(json.dumps(response, indent=4))
        else:
            st.write("Organization ID is required for deletion.")

    else:
        st.write("Method not recognized.")


# # **MAIN FUNCTION**

# In[12]:










# Setting up the page
st.title("LLM-based Query Processor")


# Streamlit UI
user_query = st.text_input("Enter your query:")

def main():

    components = classify_query(user_query)
    st.write(f"Identified components by OpenAI LLM: {components}")

    if len(components) > 1:
        handle_multi_component_query(user_query, components)
    elif 'activity' in components:
        handle_activity_query(user_query)
    elif 'stage' in components:
        handle_stage_query(user_query)
    elif 'deal' in components:
        handle_deal_query(user_query)
    elif 'organization' in components:
        handle_organization_query(user_query)
    elif 'person' in components:
        handle_person_query(user_query)
    else:
        st.write("Could not classify the query")

if st.button("Process Query"):
    try:
        main()
    except Exception as e:
        st.write("Please Try Again")

