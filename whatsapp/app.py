import os
import json
from dotenv import load_dotenv
from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mpesa import MpesaAPI
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from flask_mpesa import MpesaAPI
from blockchain import create_account, send_eth, format_address

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bima.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
app.config['SECRET_KEY'] = "myverysecretkey"
app.config["API_ENVIRONMENT"] = "sandbox" #sandbox or live
app.config["APP_KEY"] = "UMLYSVYrOHiF0A705sxGZreAL8ISzaA7" # App_key from developers portal
app.config["APP_SECRET"] = "KSiJ65bGtapUEQeg" #App_Secret from developers portal

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mpesa_api=MpesaAPI(app)

welcome = ["hi", "hey", "hello", "hallo", "ola", "jambo"]
hospital_text = "Which hospital would you prefer to deliver your baby from? \n\n 1.Matter Hospital      KES 10,000 \n 2.Aga Khan Hospital      KES 20,000 \n 3.Guru Nanak Hospital      KES 8,000"
hospitals = [
    {
        "name": "Matter Hospital",
        "price": "10,000"
    },
    {
        "name": "Aga Khan Hospital",
        "price": "10,000"
    },
    {
        "name": "Guru Nanak Hospital",
        "price": "8,000"
    },
]

contribution_text = "How often would you like to make the contributions? \n\n 1. Daily \n 2. Weekly \n 3. Monthly"
contributions = ["Daily", "Weekly", "Monthly"]
home_menu = "1. Make Payment \n 2. View Balance"

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    names = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    hospital = db.Column(db.Integer)
    contribution_frequency = db.Column(db.String(20), default="monthly")
    key = db.Column(db.String(1000))


client = Client(account_sid, auth_token)

def response(message):
    response = MessagingResponse()
    response.message(message)
    return str(response)

@app.route('/message', methods=['POST'])
def reply():
    message = request.form.get('Body').lower()
    phone = request.form.get('WaId')
    user = User.query.filter_by(phone=phone).first()
    if message == "exit":          
        if session.get(phone):
            session.pop(phone)
            return response("User deleted successfuly")

    if not user:
        signup_response = signup_flow(request)
        return signup_response

    if message in welcome:  
        user = User.query.filter_by(phone=phone).first()
        nl = "\n"
        return response(f"Welcome back to Bima {user.names} What would you like to do today? {nl + nl } {home_menu}")

    if message == "1" or session[phone]["action"] == "make_payment":
        return str(make_payment(request, user))

    elif message == "2":
        view_balance(request)
    
def signup_flow(request):
    message = request.form.get('Body').lower()
    phone = request.form.get('WaId')
    if message in welcome:
        return response(f"Welcome to Bima, we believe that maternal care should be accesible for all. \n\n You're number {phone} is not registered. Type *Yes* to start preparing for you're coming new born.")
    elif not session.get(phone):
        feedback = registration_step_one(request)
        if feedback:
            session[phone] = {"state": 1, "data": None}
            return str(feedback)
        return str(response("Something wrong happened"))

    elif session.get(phone)["state"] == 1:
        feedback = register_user_names(request)
        if feedback:
            user_data = session.get(phone)
            user_data["state"] = 2
            session[phone] = user_data
            return str(feedback)
        else:
            return str(response("Something wrong happened"))

    elif session.get(phone)["state"] == 2:
        feedback = register_user_hospital(request)
        if feedback:
            user_data = session.get(phone)
            user_data["state"] = 3
            session[phone] = user_data
            return str(feedback)
        else:
            return str(response("Something wrong happened"))
    
    elif session.get(phone)["state"] == 3:
        feedback = register_user_payment_frequency(request)
        if feedback:
            user_data = session.get(phone)
            user_data["state"] = 4
            session[phone] = user_data
            return str(feedback)
        else:
            return str(response("Something wrong happened"))

    elif session.get(phone)["state"] == 4:
        feedback = register_user_on_db(request)
        if feedback:
            return str(feedback)
        else:
            return str(response("Something wrong happened"))
        
def registration_step_one(request):
    message = request.form.get('Body').lower()
    if message == "yes":
        return response("Enter your full names")

def register_user_names(request):
    message = request.form.get('Body').lower()
    phone = request.form.get('WaId')
    user_data = session.get(phone)
    user_data["data"] = message
    return response(hospital_text)

def register_user_hospital(request):
    message = request.form.get('Body').lower()
    phone = request.form.get('WaId')
    user_data = session.get(phone)
    user_data["data"] += "*"+ message
    return response(contribution_text)

def register_user_payment_frequency(request):
    message = request.form.get('Body').lower()
    phone = request.form.get('WaId')
    user_data = session.get(phone)
    user_data["data"] += "*"+ message
    all_data = user_data["data"].split("*")
    names = all_data[0].title()
    hospital = int(all_data[1])
    payments = int(all_data[2])
    
    nl = '\n'
    return response(f"Confirm your details are correct {nl + nl} Names: {names} {nl} Hospital: {hospitals[hospital - 1]['name']} {nl} Payment frequency: { contributions[payments - 1]} {nl + nl} 1. Accept {nl} 2. Decline")

def register_user_on_db(request):
    message = request.form.get('Body').lower()
    if message == "1":
        phone = request.form.get('WaId')
        user_data = session.get(phone)
        all_data = user_data["data"].split("*")
        names = all_data[0].title()
        hospital = int(all_data[1])
        payments = int(all_data[2])
        user_blockchain_account = create_account("123@Iiht")
        user = User(names=names, phone=phone,contribution_frequency = payments, hospital = hospital, key = json.dumps(user_blockchain_account))
        db.session.add(user)
        db.session.commit()
        session.pop(phone)
        return response(f"Congratulations, your Bima account is set up. Here are some of the things you can do. \n\n\n {home_menu}")
    else:
        return response("Sad to you leave, goodbye")

def make_payment(request, user):
    # We are only focusing on Kenyan Fiat Onramp
    sesh = session.get(user.phone)
    if not sesh:
        session[user.phone] = { "action": "make_payment", "state": 1 ,"data": None}
        return response(f"Your contribution frequency is KES 25 {contributions[int(user.contribution_frequency) -1].lower()}, how much would you like to contribute today?")
    elif sesh["state"] == 1:
        message = request.form.get('Body').lower()
        if not float(message):
            return response("You have entered wrong amount. Try again later.")
        sesh["data"] = message
        sesh["state"] = 2 
        session[user.phone] = sesh
        nl = "\n"
        return response(f"You are about to contribute {message} from your number {user.phone} {nl + nl} 1. Accept {nl} 2. Decline")
    elif sesh["state"] == 2:
        amount = sesh["data"]
        return response(mpesa_prompt(user.phone, amount))

def mpesa_prompt(phone, amount):
    data = {
        "business_shortcode": "174379", #from developers portal
        "passcode": "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919",#from developers portal
        "amount": amount, # choose amount preferrably KSH 1
        "phone_number": phone, #phone number to be prompted to pay
        "reference_code": "XXXXXXXX",#Code to inform the user of services he/she is paying for.
        "callback_url": "https://8ef9-102-220-12-50.ngrok.io/payments/mpesa/callback_url", # cllback url should be exposes. for testing putposes you can route on host 0.0.0.0 and set the callback url to be https://youripaddress:yourport/endpoint
        "description": "On rails" #a description of the transaction its optional
    }

    resp = mpesa_api.MpesaExpress.stk_push(**data)  # ** unpacks the dictionary
    return "You will receive a message from us once we receive the money."

def view_balance():
    pass

@app.route("/payments/mpesa/callback_url", methods=["POST"])
def mpesa_callback():
    #get json data set to this route
    json_data = request.get_json()
    #get result code and probably check for transaction success or failure
    result_code=json_data["Body"]["stkCallback"]["ResultCode"]
    print(json_data["Body"])
    if result_code == 0:
        phone = json_data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][4]["Value"]
        print(phone)
        amount = json_data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"]
        user = User.query.filter_by(phone=phone).first()
        print("Our user key is")
        print(user.key)
        user_blockchain_account = format_address(f'0x{json.loads(user.key)["address"]}')
        response = send_eth(user_blockchain_account, amount)
        print(response)
        if response[0]:
            message = client.messages.create(
                                body=f'We have received KES {amount} from you for your Bima account! Your wallet has been deposited with the equivalent ether',
                                from_='+17126247756',
                                to=f'+{phone}'
            )
        else:
            message = client.messages.create(
                                body=f'{response[1]}',
                                from_='+17126247756',
                                to=f'+{phone}'
            )
        return response(message)
    else:
        print("Something wrong happened")
        return response("Something wrong happened")
        

if __name__ == "__main__":
    app.run()   