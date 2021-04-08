from app import db
from datetime import datetime

class JUser:
    def __init__(self, user_id):
        self.user_id = user_id
        self.jbucks = 0
        self.daily_value = 1
        self.daily_available = True
        self.load(db.user.find_one({'user_id': user_id}))

    def load(self, doc):
        if not doc:
            return
        self.jbucks = doc.get('jbucks', self.jbucks)
        self.daily_value = doc.get('daily_value', self.daily_value)
        self.daily_available = doc.get('daily_available', self.daily_available)

    def daily(self):
        self.daily_available = False
        self.add_jbucks(daily_value)
        if self.daily_value < 5:
            self.daily_value += 1

    def add_jbucks(self, amt):
        self.jbucks += amt

    def save(self):
        new_doc = {
            'user_id': self.user_id,
            'jbucks': self.jbucks,
            'daily_value': self.daily_value,
            'daily_available': self.daily_available,
        }
        db.user.replace_one({'user_id': self.user_id}, new_doc, True)
