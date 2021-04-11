from app import db
from doc import Doc

class JUser(Doc):
    collection = db.user
    def __init__(self, user_id):
        self.user_id = user_id
        self.jbucks = 0
        self.daily_value = 1
        self.daily_available = True
        self.raffle_tickets = 0
        self.load(db.user.find_one({'user_id': user_id}))

    def primary_fil(self):
        return {'user_id': self.user_id}

    def daily(self):
        self.daily_available = False
        self.add_jbucks(self.daily_value)
        msg = 'You have gained {} Jbucks. You now have {} Jbucks'.format(self.daily_value, round(self.jbucks, 2))
        if self.daily_value < 5:
            self.daily_value += 1
        return msg

    def add_jbucks(self, amt):
        self.jbucks += amt

    def add_tickets(self, amt):
        if self.raffle_tickets == 0:
            self.raffle_tickets = 10
        self.raffle_tickets += amt
