from os import unlink
from tempfile import NamedTemporaryFile


class TemporaryFileHandler:
    def __init__(self):
        self.f = NamedTemporaryFile(mode="w", delete=False)
        self.name = self.f.name

    def singleWrite(self, text):
        self.f.write(text)
        self.f.close()

    def __del__(self):
        unlink(self.f.name)
