class Doc(object):
    def primary_fil(self):
        return {}
    def load(self, doc):
        if not doc:
            return
        for k, v in doc.items():
            setattr(self, k, v)
    def save(self):
        self.collection.replace_one(self.primary_fil(), vars(self), True)
