from app import db
from doc import Doc

class Job(Doc):
    collection = db.jobs
    def __init__(self, job_id=0):
        self._id = job_id
        self.income = 0
        self.repeats = 'never'
        self.name = 'Default Name'
        self.description = 'Default Description'
        self.employer = 0
        self.accepted = 0
        if job_id:
            self.load(db.user.find_one({'_id': job_id}))

    def primary_fil(self):
        return {'_id': self._id}
