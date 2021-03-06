"""
shiftex restlike package
===================

Containing restlike api for connection to jQuery frontend

"""

from flask import Blueprint
from flask_restful import Api

restlike = Blueprint("restlike", __name__)
api = Api()

from shiftex.restlike import routes
