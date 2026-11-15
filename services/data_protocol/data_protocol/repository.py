"""Participant persistence operations."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import Participant, Recording


class ParticipantRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, pseudonym: str) -> Participant:
        participant = Participant(pseudonym=pseudonym)
        self.session.add(participant)
        self.session.flush()
        return participant

    def get(self, participant_id):
        return self.session.get(Participant, participant_id)

    def list(self, limit: int, offset: int):
        return self.session.scalars(select(Participant).order_by(Participant.id).limit(limit).offset(offset)).all()


class RecordingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, participant_id, sample_rate_hz, samples_count, checksum):
        recording = Recording(participant_id=participant_id, sample_rate_hz=sample_rate_hz,
                              sample_count=samples_count, artifact_sha256=checksum)
        self.session.add(recording)
        self.session.flush()
        return recording

    def get(self, recording_id):
        return self.session.get(Recording, recording_id)

    def list(self, participant_id, limit, offset):
        query = select(Recording)
        if participant_id is not None:
            query = query.where(Recording.participant_id == participant_id)
        return self.session.scalars(query.order_by(Recording.id).limit(limit).offset(offset)).all()


class ResearchRepository:
    """Parameterized SQL for transactional, database-enforced split rules."""

    def __init__(self, session: Session):
        self.session = session

    def create_protocol(self, name, version, gesture_codes):
        return self.session.execute(text("""INSERT INTO data_protocol.protocol_versions (id, name, version, gesture_codes)
            VALUES (:id, :name, :version, :gestures) RETURNING id, name, version, gesture_codes"""),
            {"id": uuid.uuid4(), "name": name, "version": version, "gestures": gesture_codes}).mappings().one()

    def create_segment(self, recording_id, gesture_code, repetition_key, start_sample, end_sample):
        return self.session.execute(text("""INSERT INTO data_protocol.labelled_segments
            (id, recording_id, gesture_code, repetition_key, start_sample, end_sample)
            VALUES (:id, :recording_id, :gesture_code, :repetition_key, :start_sample, :end_sample)
            RETURNING id, recording_id, gesture_code, repetition_key, start_sample, end_sample"""),
            {"id": uuid.uuid4(), "recording_id": recording_id, "gesture_code": gesture_code,
             "repetition_key": repetition_key, "start_sample": start_sample, "end_sample": end_sample}).mappings().one()

    def create_manifest(self, name, version, protocol_id):
        return self.session.execute(text("""INSERT INTO data_protocol.research_manifests (id, name, version, protocol_id)
            VALUES (:id, :name, :version, :protocol_id) RETURNING id, name, version, protocol_id, state, checksum"""),
            {"id": uuid.uuid4(), "name": name, "version": version, "protocol_id": protocol_id}).mappings().one()

    def assign_participant(self, manifest_id, participant_id, category):
        return self.session.execute(text("""INSERT INTO data_protocol.manifest_participants (manifest_id, participant_id, category)
            VALUES (:manifest_id, :participant_id, :category) RETURNING manifest_id, participant_id, category"""),
            {"manifest_id": manifest_id, "participant_id": participant_id, "category": category}).mappings().one()

    def add_unit(self, manifest_id, participant_id, category, segment_id, role):
        return self.session.execute(text("""INSERT INTO data_protocol.manifest_units (id, manifest_id, participant_id, category, segment_id, role)
            VALUES (:id, :manifest_id, :participant_id, :category, :segment_id, :role)
            RETURNING id, manifest_id, participant_id, category, segment_id, role"""),
            {"id": uuid.uuid4(), "manifest_id": manifest_id, "participant_id": participant_id,
             "category": category, "segment_id": segment_id, "role": role}).mappings().one()

    def get_manifest(self, manifest_id):
        return self.session.execute(text("SELECT id, name, version, protocol_id, state, checksum FROM data_protocol.research_manifests WHERE id = :id"), {"id": manifest_id}).mappings().one_or_none()

    def freeze_manifest(self, manifest_id):
        return self.session.execute(text("""UPDATE data_protocol.research_manifests SET state = 'frozen'
            WHERE id = :id AND state = 'draft' RETURNING id, name, version, protocol_id, state, checksum"""),
            {"id": manifest_id}).mappings().one_or_none()

    def frozen_snapshot(self, manifest_id):
        manifest = self.session.execute(text("""SELECT m.id, m.name, m.version, m.state, m.checksum,
            p.id AS protocol_id, p.name AS protocol_name, p.version AS protocol_version, p.gesture_codes
            FROM data_protocol.research_manifests m JOIN data_protocol.protocol_versions p ON p.id = m.protocol_id
            WHERE m.id = :id AND m.state = 'frozen'"""), {"id": manifest_id}).mappings().one_or_none()
        if manifest is None:
            return None
        units = self.session.execute(text("""SELECT u.id, u.participant_id, u.category, u.role, s.id AS segment_id,
            s.recording_id, s.gesture_code, s.repetition_key, s.start_sample, s.end_sample,
            r.sample_rate_hz, r.sample_count, r.artifact_sha256
            FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
            JOIN data_protocol.recordings r ON r.id = s.recording_id
            WHERE u.manifest_id = :id ORDER BY u.id"""), {"id": manifest_id}).mappings().all()
        return {**dict(manifest), "units": [dict(unit) for unit in units]}

    def create_calibration(self, manifest_id, participant_id, selection_version, budget_per_gesture):
        return self.session.execute(text("""INSERT INTO data_protocol.calibration_subsets
            (id, manifest_id, participant_id, selection_version, budget_per_gesture)
            VALUES (:id, :manifest_id, :participant_id, :selection_version, :budget)
            RETURNING id, manifest_id, participant_id, selection_version, budget_per_gesture, state"""),
            {"id": uuid.uuid4(), "manifest_id": manifest_id, "participant_id": participant_id,
             "selection_version": selection_version, "budget": budget_per_gesture}).mappings().one()

    def add_calibration_item(self, subset_id, unit_id):
        return self.session.execute(text("""INSERT INTO data_protocol.calibration_items (subset_id, unit_id)
            VALUES (:subset_id, :unit_id) RETURNING subset_id, unit_id"""),
            {"subset_id": subset_id, "unit_id": unit_id}).mappings().one()

    def freeze_calibration(self, subset_id):
        return self.session.execute(text("""UPDATE data_protocol.calibration_subsets SET state = 'frozen'
            WHERE id = :id AND state = 'draft'
            RETURNING id, manifest_id, participant_id, selection_version, budget_per_gesture, state"""),
            {"id": subset_id}).mappings().one_or_none()

    def get_calibration(self, subset_id):
        subset = self.session.execute(text("""SELECT id, manifest_id, participant_id, selection_version, budget_per_gesture, state
            FROM data_protocol.calibration_subsets WHERE id = :id"""), {"id": subset_id}).mappings().one_or_none()
        if subset is None:
            return None
        units = self.session.execute(text("SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = :id ORDER BY unit_id"), {"id": subset_id}).scalars().all()
        durations = self.session.execute(text("""SELECT gesture_code, unique_seconds FROM data_protocol.calibration_durations
            WHERE subset_id = :id ORDER BY gesture_code"""), {"id": subset_id}).mappings().all()
        return {**dict(subset), "unit_ids": units, "durations": [dict(row) for row in durations]}
