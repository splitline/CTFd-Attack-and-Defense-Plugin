from flask import Blueprint, jsonify, request, abort

from CTFd.models import Challenges, Solves, Awards, Teams, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.plugins.migrations import upgrade
from CTFd.utils.dates import ctf_paused, ctf_ended, ctf_started

from datetime import datetime
import secrets

import requests
import os


class AWDChallenge(Challenges):
    __mapper_args__ = {"polymorphic_identity": "awd_challenge"}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    defense_point = db.Column(db.Integer, default=5)
    token = db.Column(db.Text)

    def __init__(self, *args, **kwargs):
        super(AWDChallenge, self).__init__(**kwargs)
        self.value = 0
        self.token = secrets.token_hex(16)


class AttackAndDefenseChallenge(BaseChallenge):
    id = "awd_challenge"  # Unique identifier used to register challenges
    name = "awd_challenge"  # Name of a challenge type
    templates = {  # Handlebars templates used for each aspect of challenge editing & viewing
        "create": "/plugins/awd/assets/create.html",
        "update": "/plugins/awd/assets/update.html",
        "view": "/plugins/awd/assets/view.html",
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": "/plugins/awd/assets/create.js",
        "update": "/plugins/awd/assets/update.js",
        "view": "/plugins/awd/assets/view.js",
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = "/plugins/awd/assets/"
    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        "awd_challenge",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = AWDChallenge

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = AWDChallenge.query.filter_by(id=challenge.id).first()
        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "description": challenge.description,
            "connection_info": challenge.connection_info,
            "category": challenge.category,
            "state": challenge.state,
            "max_attempts": challenge.max_attempts,
            "type": challenge.type,
            "type_data": {
                "id": cls.id,
                "name": cls.name,
                "templates": cls.templates,
                "scripts": cls.scripts,
            },
        }
        return data

    @classmethod
    def delete(cls, challenge):
        super(AttackAndDefenseChallenge, cls).delete(challenge)
        Awards.query.filter_by(name=challenge.name,
                               category='[A&D] Attack').delete()
        Awards.query.filter_by(name=challenge.name,
                               category='[A&D] Defense').delete()
        db.session.commit()


def patch_methods():
    def get_awd_awards(self):
        from CTFd.utils import get_config
        attack = Awards.query.filter(
            Awards.team_id == self.id,
            Awards.category == '[AWD] Attack'
        ).order_by(Awards.date.desc())
        defense = Awards.query.filter(
            Awards.team_id == self.id,
            Awards.category == '[AWD] Defense'
        ).order_by(Awards.date.desc())
        freeze = get_config("freeze")
        if freeze:
            dt = datetime.datetime.utcfromtimestamp(freeze)
            attack = attack.filter(Awards.date < dt)
            defense = defense.filter(Awards.date < dt)
        return {
            'attack': attack.all(),
            'defense': defense.all()
        }

    def get_score(self, admin=False):
        score = 0
        for member in self.members:
            score += member.get_score(admin=admin)

        awd_score = db.session.query(
            db.func.sum(Awards.value).label("score")
        ).filter((Awards.category == '[AWD] Attack') | (Awards.category == '[AWD] Defense'), Awards.team_id == self.id).first().score

        score += int(awd_score or 0)
        return score

    Teams.get_score = get_score
    Teams.get_awd_awards = get_awd_awards


def replace_templates():
    from CTFd.utils.plugins import override_template
    dir_path = os.path.dirname(os.path.realpath(__file__))

    override_template("admin/teams/team.html",
                      open(dir_path + "/templates/admin_team.html").read())
    override_template("teams/public.html",
                      open(dir_path + "/templates/team_public.html").read())


def load(app):
    patch_methods()
    replace_templates()

    upgrade()
    app.db.create_all()

    @app.route('/plugins/awd/api/scoreboard/<chal_name>')
    def scoreboard_api(chal_name):
        awd_pts = db.session.query(
            Awards.team_id.label("id"),
            Teams.name.label("team_name"),
            db.func.sum(
                db.case([(Awards.category == '[AWD] Attack', Awards.value)])
            ).label('attack'),
            db.func.sum(
                db.case([(Awards.category == '[AWD] Defense', Awards.value)])
            ).label('defense'),
            db.func.sum(Awards.value).label("score"),
            db.func.max(Awards.date).label("date")
        ).filter(
            Awards.name == chal_name,
            Teams.id == Awards.team_id,
            (Awards.category == '[AWD] Attack') | (Awards.category == '[AWD] Defense')
        ).group_by(Awards.team_id).order_by(db.desc("score"), db.desc("date")).all()
        # print(awd_pts)
        return jsonify([[n[0], n[1], int(n[2] or 0), int(n[3] or 0), int(n[4] or 0), n[5].timestamp()] for n in awd_pts])

    @app.route('/plugins/awd/api/update', methods=['GET', 'POST'])
    def awd_update():
        if not ctf_started() or ctf_paused() or ctf_ended():
            return jsonify({'success': False, 'message': 'CTF is paused or ended'})

        '''
        json format:
        {
            "id": 123,
            "token": "deadbeef",
            "attacks": {
                <team-id>, <points>,
                <team-id>: <points>
            },
            "defenses": [ <team-id>, <team-id>, ... ]
        }
        '''
        data=request.json
        chal_id=data['id']
        token=data['token']

        challenge=AWDChallenge.query.filter_by(id=chal_id).first()
        if challenge is None:
            return jsonify({'success': False, 'message': 'Challenge not found'})

        if challenge.token != token:
            return jsonify({'success': False, 'message': 'Invalid token'})

        if challenge.state != 'visible':
            return jsonify({'success': False, 'message': 'Challenge is hidden'})

        for team_id, points in data['attacks'].items():
            if points == 0:
                continue
            team=Teams.query.filter_by(id=team_id).first()
            if team is None:
                continue
            award=Awards(name=challenge.name, value=int(points),
                           team_id=team.id, icon='lightning', category='[AWD] Attack')
            db.session.add(award)
            print(f"[+] {team.name} attacked {award.name} for {points}.")

        for team_id in data['defenses']:
            team=Teams.query.filter_by(id=team_id).first()
            if team is None:
                continue
            award=Awards(name=challenge.name, value=int(challenge.defense_point),
                           team_id=team.id, icon='shield', category='[AWD] Defense')
            db.session.add(award)
            print(f"[+] {team.name} defensed {award.name}.")

        db.session.commit()
        return jsonify({'success': True})

    awd_update._bypass_csrf=True

    CHALLENGE_CLASSES["awd_challenge"]=AttackAndDefenseChallenge
    register_plugin_assets_directory(
        app, base_path="/plugins/awd/assets/"
    )

    if getattr(db, 'app', None) == None:
        db.app=app
