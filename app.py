from flask import Flask, request, jsonify, session
from twilio.twiml.messaging_response import MessagingResponse
import time
import openai
import json
import requests
import os
from dotenv import load_dotenv
load_dotenv("/etc/secrets/openapi")

openai.api_key = os.getenv("openapi")

# slots = [
#     Slot(
#         Name="Dr. Ritika",
#         id = 987,
#         time=["8:00","9:00","10:00","11:00","12:00","14:00","15:00","16:00","17:00"],
#         booked=[],
#     ),
#     Slot(
#         Name="Dr.Johnson",
#         id = 2,
#         time=["10am","12pm","2pm","3pm","4pm","5pm"],
#         booked=["11am"],
#     )
# ]


def get_moderation(question):
    errors = {
        "hate": "Content that expresses, incites, or promotes hate based on race, gender, ethnicity, religion, nationality, sexual orientation, disability status, or caste.",
        "hate/threatening": "Hateful content that also includes violence or serious harm towards the targeted group.",
        "self-harm": "Content that promotes, encourages, or depicts acts of self-harm, such as suicide, cutting, and eating disorders.",
        "sexual": "Content meant to arouse sexual excitement, such as the description of sexual activity, or that promotes sexual services (excluding sex education and wellness).",
        "sexual/minors": "Sexual content that includes an individual who is under 18 years old.",
        "violence": "Content that promotes or glorifies violence or celebrates the suffering or humiliation of others.",
        "violence/graphic": "Violent content that depicts death, violence, or serious physical injury in extreme graphic detail.",
    }
    response = openai.Moderation.create(input=question)
    if response.results[0].flagged:
        # get the categories that are flagged and generate a message
        result = [
            error
            for category, error in errors.items()
            if response.results[0].categories[category]
        ]
        return result
    return None

def book_apt(id, time):
    requests.post("https://hospital-dilg.onrender.com/patient/bookAppointement", json={
        "Id": str(id),
        "StartTime": str(time),
        "Endtime": time.split(":")[0]+":30",
        "Date": "2023-09-23"
    })
    return f"Your appointment has been booked at {time}."
            # elif (time not in timeslot) and (time in bookedslot):
            #     print(f"The doctor is already booked at that time. Choose another time slot. Here are the available slots: {timeslot}. ")
            # elif (time not in timeslot) and (time not in bookedslot):
            #     print(f"The doctor will not be available at the hospital at that time. Choose another time slot. Here are the available slots: {timeslot}.")

def list_doctors(specialization):
    # matching_doctors = []
    # for doctor in doctors:
    #     if specialization in doctor.Specialization:
    #         matching_doctors.append(doctor)
    
    # print(matching_doctors)

    # # Extract the names of matching doctors
    # doctor_names = [doctor.Name for doctor in matching_doctors]
    data = requests.post("https://hospital-dilg.onrender.com/hospital/doctors", json={
        "Id": "12345"
    })
    result = data.json()['doctors']
    stringres = ""
    for doctor in result:
        stringres=f"Name: {doctor['Name']}\nDesignation: {doctor['Designation']}\nDuty Hours:\n"
        stringres+=f"{doctor['DutyHour']['StartTime']} - {doctor['DutyHour']['EndTime']}\n"
        stringres+=f"{doctor['Designation']}\n\n"

    
    # if doctor_names:
    #     response = "\n".join([f"{i+1}. {name}" for i, name in enumerate(doctor_names)])
    # else:
    #     response = f"I'm sorry, but there are no {specialization} specialists in our database."

    return stringres

def bookappointment(question):
    messages = [{"role": "user", "content": question}]  # Initial user query
    functions = [
        {
            "name": "book_apt",
            "description": "Book an appointment for a doctor",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "ID of the doctor extracted from user query",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time extracted from user query",
                    },
                },
                "required": ["id","time"],
            },
        }
    ]
        
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0613",
        messages=messages,
        functions=functions,
        function_call="auto",  # Auto-detect function calls
    )
    response_message = response["choices"][0]["message"]

    # Check if GPT wanted to call a function
    if response_message.get("function_call"):
        function_name = response_message["function_call"]["name"]

        if function_name == "book_apt":
            # Handle the list_doctors function
            available_functions = {
                "book_apt": book_apt,
            }
            function_to_call = available_functions[function_name]
            function_args = json.loads(response_message["function_call"]["arguments"])
            function_response = function_to_call(
                id=function_args.get("id"),
                time=function_args.get("time")
            )

        # Format the function response into a response message
        response_message = {
            "role": "assistant",
            "content": function_response,
        }
    # Extend the conversation with the assistant's reply
    messages.append(response_message)
    return response_message

def answer_patient_query(instructions,  previous_questions_and_answers, new_question):
    # build the messages
    messages = [
        { "role": "system", "content": instructions },
    ]
    # add the previous questions and answers
    for question, answer in previous_questions_and_answers[-MAX_CONTEXT_QUESTIONS:]:
        messages.append({ "role": "user", "content": question })
        messages.append({ "role": "assistant", "content": answer })
    # add the new question
    messages.append({ "role": "user", "content": new_question })

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0613",
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        top_p=1,
        frequency_penalty=FREQUENCY_PENALTY,
        presence_penalty=PRESENCE_PENALTY,
    )
    return completion.choices[0].message.content

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("twiliokey")
@app.route("/")
def greet():
    return "Hello World"

@app.route('/bot', methods=['POST'])
def bot():
    print(os.getenv("twiliokey"))
    incoming_msg = request.values.get('Body', '').lower()
    resp = MessagingResponse()
    msg = resp.message()

    # Initialize the session if it doesn't exist
    if 'step' not in session:
        session['step'] = 0

    step = session['step']
    c = 0
    if "help" in incoming_msg.lower():
        msg.body('''Greetings. Welcome to the emergency bot interface. How may I help you?\n1.Immediate ambulance arrangement.\n2. First aid help''')
        step=1
    elif step == 1 and "1" in incoming_msg:
        msg.body('''You have selected immediate ambulance arrangement. How far is the nearest hospital from your location?\n\n\na. <5km\nb. bkm-20km\nc. >20km''')
        step = 2
        c = 1
    elif step == 1 and "2" in incoming_msg:
        msg.body('''You have selected first aid help. What would you be requiring?\n1. Contact an on-call doctor\n2. Require medicines immediately''')
        step = 2
        c = 2
    elif "a" in incoming_msg:
        msg.body('''You are within 5km of the nearest hospital. Please stay on the line while we arrange an ambulance for you.''')
        time.sleep(5)
        msg.body('''An ambulance has been arranged, and will reach you at the earliest.''')
        step = 3
    elif "b" in incoming_msg:
        msg.body('''You are between 5km and 20km of the nearest hospital. Please stay on the line while we arrange an ambulance for you.''')
        time.sleep(5)
        msg.body('''An ambulance has been arranged, and will reach you at the earliest.''')
        step = 3
    elif "c" in incoming_msg:
        msg.body('''You are farther than 20km of the nearest hospital. Please stay on the line while we arrange an ambulance for you. Do call 112 
                    if the wait time is too long and the patient's condition is deteriorating''')
        time.sleep(5)
        msg.body('''An ambulance has been arranged, and will reach you at the earliest.''')
        step = 3
    elif "i" in incoming_msg:
        msg.body('''A general physician is available. Contact xxxxxxxxxx now''')
        step = 3
    elif "ii" in incoming_msg:
        msg.body('''Here is your nearest pharmacy's contact : xxxxxxxxxx''')
        step = 3
    if step==3:
        msg.body("Thank you for your patience. Hope your problem was resolved to the best ability")
    
    return str(resp)

@app.route('/chat')
def hello_world():
    print(os.getenv("openapi"))
    query = request.args['query']
    if ("book appointment"  or "appointment" or "book" or "schedule" in query):
        res = bookappointment(query)
        return jsonify({
            "content": res['content']
        })
    elif ("doctor list" or "list of doctors" or "nearby doctors" in query):
        res = list_doctors("Generic")
        return jsonify({
            "content": res['content']
        })
    else:
        res = answer_patient_query(query)
        return jsonify({
            "content": res['content']
        })
