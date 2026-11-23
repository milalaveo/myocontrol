"""Relational acceptance tests: use only a disposable review database."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
HASH = "a" * 64
CONTRACT = {"version": "time-domain-4ch-v1", "channels": 4}


class CloudDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.c = psycopg.connect(os.environ["TEST_DATABASE_URL"])
        if not self.c.execute("SELECT current_database()").fetchone()[0].startswith("myocontrol_review_"):
            self.c.close()
            self.fail("Disposable review database required")
        self.operator, self.client, self.manifest, self.target = [uuid.uuid4() for _ in range(4)]
        self.c.execute("INSERT INTO identity.operators(id,email,display_name,password_hash) VALUES (%s,%s,'Reviewer test',%s)",
                       (self.operator, f"{self.operator}@example.test", "$argon2id$v=19$m=65536,t=3,p=1$test-salt$test-digest"))
        self.c.execute("INSERT INTO identity.clients(id,operator_id,kind,name,platform) VALUES (%s,%s,'desktop','Test desktop','test-os')",
                       (self.client, self.operator))

    def tearDown(self):
        self.c.rollback()
        self.c.close()

    def reject(self, statement, params=()):
        with self.assertRaises(psycopg.Error):
            with self.c.transaction():
                self.c.execute(statement, params)
                self.c.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def flush(self):
        self.c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.c.execute("SET CONSTRAINTS ALL DEFERRED")

    def run_record(self, kind="source_train", family="lda", condition="source_only", parent=None, calibration=None, model=None):
        run = uuid.uuid4()
        self.c.execute("""INSERT INTO ml_experiments.experiment_runs
            (id,operator_id,submission_key,kind,family,condition,execution_location,manifest_id,manifest_sha256,
             target_participant_id,calibration_subset_id,parent_model_id,evaluated_model_id,feature_contract,input_snapshot,parameters,seed,software_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'review-test-v1')""",
            (run,self.operator,str(run),kind,family,condition,"desktop" if kind=="personalise" else "local_workstation",
             self.manifest,HASH,self.target,calibration,parent,model,Jsonb(CONTRACT),Jsonb({"source": "synthetic"}),Jsonb({})))
        return run

    def claim(self, run, location="local_workstation"):
        actual=self.c.execute("SELECT ml_experiments.claim_experiment(%s,%s,%s,%s)",
                              (self.operator,self.client,HASH,location)).fetchone()[0]
        self.assertEqual(actual,run)

    def artifact(self, verified=True):
        artifact=uuid.uuid4()
        self.c.execute("INSERT INTO ml_experiments.artifacts(id,operator_id,storage_key,sha256,size_bytes,media_type) VALUES (%s,%s,%s,%s,100,'application/json')",
                       (artifact,self.operator,str(artifact),HASH))
        if verified:
            self.c.execute("UPDATE ml_experiments.artifacts SET state='verified',verified_at=clock_timestamp() WHERE id=%s",(artifact,))
        return artifact

    def model_draft(self,run,method="none",verified=True):
        model=uuid.uuid4()
        self.c.execute("INSERT INTO ml_experiments.model_versions(id,run_id,artifact_id,name,adaptation_method) VALUES (%s,%s,%s,'Test model',%s)",
                       (model,run,self.artifact(verified),method))
        for pos,code in enumerate(["rest","fist"]):
            self.c.execute("INSERT INTO ml_experiments.model_classes VALUES (%s,%s,%s)",(model,code,pos))
        return model

    def publish(self,run,model):
        self.c.execute("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH))
        self.c.execute("UPDATE ml_experiments.model_versions SET state='published',published_at=clock_timestamp() WHERE id=%s",(model,))
        self.flush()

    def source_model(self):
        run=self.run_record();self.claim(run)
        model=self.model_draft(run);self.publish(run,model)
        return model

    def test_account_hash_email_and_disabled_access(self):
        self.reject("UPDATE identity.operators SET password_hash='plaintext' WHERE id=%s",(self.operator,))
        self.reject("UPDATE identity.operators SET email='UPPER@example.test' WHERE id=%s",(self.operator,))
        self.c.execute("INSERT INTO identity.access_sessions(operator_id,client_id,token_sha256,scope,expires_at) VALUES (%s,%s,%s,'desktop',CURRENT_TIMESTAMP+interval '1 hour')",
                       (self.operator,self.client,HASH))
        self.assertEqual(self.c.execute("SELECT count(*) FROM identity.valid_session_ids WHERE operator_id=%s",(self.operator,)).fetchone()[0],1)
        self.c.execute("UPDATE identity.operators SET state='disabled' WHERE id=%s",(self.operator,))
        self.assertEqual(self.c.execute("SELECT count(*) FROM identity.valid_session_ids WHERE operator_id=%s",(self.operator,)).fetchone()[0],0)

    def test_session_scope_owner_expiry_and_revocation(self):
        self.reject("INSERT INTO identity.access_sessions(operator_id,client_id,token_sha256,scope,expires_at) VALUES (%s,%s,%s,'training_worker',CURRENT_TIMESTAMP+interval '1 hour')",
                    (self.operator,self.client,HASH))
        self.reject("INSERT INTO identity.access_sessions(operator_id,token_sha256,scope,expires_at) VALUES (%s,%s,'web',CURRENT_TIMESTAMP-interval '1 hour')",(self.operator,HASH))
        self.c.execute("INSERT INTO identity.access_sessions(operator_id,token_sha256,scope,expires_at) VALUES (%s,%s,'web',CURRENT_TIMESTAMP+interval '1 hour')",(self.operator,HASH))
        self.c.execute("UPDATE identity.access_sessions SET revoked_at=clock_timestamp() WHERE token_sha256=%s",(HASH,))
        self.reject("UPDATE identity.access_sessions SET revoked_at=NULL WHERE token_sha256=%s",(HASH,))
        self.reject("UPDATE identity.clients SET kind='training_worker' WHERE id=%s",(self.client,))

    def test_expired_lease_cannot_publish_and_retry_is_new_run(self):
        run=self.run_record()
        # The owner/test administrator simulates the passage of time at claim.
        self.c.execute("""UPDATE ml_experiments.experiment_runs SET status='running',worker_client_id=%s,lease_sha256=%s,
            started_at=clock_timestamp()-interval '1 hour',heartbeat_at=clock_timestamp()-interval '1 hour',
            lease_expires_at=clock_timestamp()-interval '1 minute' WHERE id=%s""",(self.client,HASH,run))
        self.reject("SELECT ml_experiments.heartbeat_experiment(%s,%s,%s)",(run,self.client,HASH))
        self.reject("SELECT ml_experiments.finish_experiment(%s,%s,%s,'failed','late result')",(run,self.client,HASH))
        self.assertEqual(self.c.execute("SELECT ml_experiments.interrupt_expired_experiments()").fetchone()[0],1)
        retry=self.run_record()
        # Identity is immutable even before start; retry relation is set at submission.
        self.reject("UPDATE ml_experiments.experiment_runs SET retry_of_id=%s WHERE id=%s",(run,retry))

    def test_run_inputs_and_submission_idempotency(self):
        run=self.run_record()
        self.reject("UPDATE ml_experiments.experiment_runs SET seed=5 WHERE id=%s",(run,))
        self.reject("""INSERT INTO ml_experiments.experiment_runs
            SELECT (jsonb_populate_record(NULL::ml_experiments.experiment_runs,
                to_jsonb(r)||jsonb_build_object('id',gen_random_uuid()))).*
            FROM ml_experiments.experiment_runs r WHERE id=%s""",(run,))
        self.reject("UPDATE ml_experiments.experiment_runs SET status='succeeded',completed_at=clock_timestamp() WHERE id=%s",(run,))

    def test_worker_lease_fencing_and_heartbeat(self):
        run=self.run_record();self.claim(run)
        self.reject("SELECT ml_experiments.finish_experiment(%s,%s,%s,'failed','error')",(run,self.client,"b"*64))
        self.c.execute("SELECT ml_experiments.heartbeat_experiment(%s,%s,%s)",(run,self.client,HASH))
        self.c.execute("SELECT ml_experiments.finish_experiment(%s,%s,%s,'failed','Synthetic failure')",(run,self.client,HASH))
        self.reject("UPDATE ml_experiments.experiment_runs SET error='changed' WHERE id=%s",(run,))

    def test_complete_source_model_and_terminal_immutability(self):
        model=self.source_model()
        self.assertEqual(self.c.execute("SELECT count(*) FROM ml_experiments.published_models WHERE id=%s",(model,)).fetchone()[0],1)
        self.reject("UPDATE ml_experiments.model_versions SET name='changed' WHERE id=%s",(model,))
        self.reject("DELETE FROM ml_experiments.model_classes WHERE model_id=%s AND code='fist'",(model,))

    def test_model_requires_verified_artifact_and_complete_run(self):
        run=self.run_record();self.claim(run);model=self.model_draft(run,verified=False)
        with self.assertRaises(psycopg.Error):
            with self.c.transaction():self.publish(run,model)
        self.reject("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH))

    def test_package_materials_required(self):
        for family,method,purpose in [("lda","lda_statistics","source_statistics"),("svm","svm_weighted","source_pool"),("mlp","mlp_replay","replay_pool")]:
            run=self.run_record(family=family);self.claim(run);model=self.model_draft(run,method)
            with self.assertRaises(psycopg.Error):
                with self.c.transaction():self.publish(run,model)
            self.c.execute("INSERT INTO ml_experiments.model_package_items VALUES (%s,%s,%s)",(model,purpose,self.artifact()))
            self.publish(run,model)
            self.reject("DELETE FROM ml_experiments.model_package_items WHERE model_id=%s",(model,))

    def test_local_personalisation_parent_and_subset(self):
        parent=self.source_model()
        self.reject("INSERT INTO ml_experiments.experiment_runs(id,operator_id,submission_key,kind,family,condition,execution_location,manifest_id,manifest_sha256,feature_contract,input_snapshot,parameters,seed,software_version) VALUES (%s,%s,'bad','personalise','lda','personalised','desktop',%s,%s,%s,'{}','{}',1,'test')",
                    (uuid.uuid4(),self.operator,self.manifest,HASH,Jsonb(CONTRACT)))
        run=self.run_record(kind="personalise",condition="personalised",parent=parent,calibration=uuid.uuid4())
        self.claim(run,"desktop");model=self.model_draft(run);self.publish(run,model)
        self.assertEqual(self.c.execute("SELECT parent_model_id FROM ml_experiments.published_models WHERE id=%s",(model,)).fetchone()[0],parent)

    def evaluation(self,model,accuracy=0.8,f1=0.8,rest=0.2,counts=(4,1,1,4)):
        run=self.run_record(kind="evaluate",model=model);self.claim(run)
        e=uuid.uuid4()
        self.c.execute("INSERT INTO ml_experiments.evaluations(id,run_id,model_id,accuracy,macro_f1,rest_false_activation_rate) VALUES (%s,%s,%s,%s,%s,%s)",(e,run,model,accuracy,f1,rest))
        for (actual,predicted),count in zip([('rest','rest'),('rest','fist'),('fist','rest'),('fist','fist')],counts):
            self.c.execute("INSERT INTO ml_experiments.confusion_counts VALUES (%s,%s,%s,%s,%s)",(e,model,actual,predicted,count))
        return run,e

    def test_evaluation_metrics_mathematically_checked(self):
        model=self.source_model();run,e=self.evaluation(model)
        self.c.execute("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH));self.flush()
        self.reject("UPDATE ml_experiments.evaluations SET accuracy=0 WHERE id=%s",(e,))
        self.assertEqual(self.c.execute("SELECT accuracy FROM ml_experiments.reviewer_results WHERE id=%s",(e,)).fetchone()[0],0.8)

    def test_wrong_metrics_incomplete_matrix_and_unknown_class_rejected(self):
        model=self.source_model();run,e=self.evaluation(model,accuracy=0.9)
        self.reject("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH))
        self.c.execute("UPDATE ml_experiments.evaluations SET accuracy=0.8 WHERE id=%s",(e,))
        self.c.execute("DELETE FROM ml_experiments.confusion_counts WHERE evaluation_id=%s AND actual_class='fist' AND predicted_class='rest'",(e,))
        self.reject("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH))
        self.reject("INSERT INTO ml_experiments.confusion_counts VALUES (%s,%s,'unknown','rest',0)",(e,model))

    def test_missing_rest_is_na_not_zero(self):
        model=self.source_model();run,e=self.evaluation(model,accuracy=1,f1=0.5,rest=0,counts=(0,0,0,5))
        self.reject("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH))
        self.c.execute("UPDATE ml_experiments.evaluations SET rest_false_activation_rate=NULL,rest_missing_reason='No rest windows' WHERE id=%s",(e,))
        self.c.execute("SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",(run,self.client,HASH));self.flush()

    def test_session_reports_are_terminal_validated_and_immutable(self):
        values=(self.operator,self.client,uuid.uuid4(),uuid.uuid4(),HASH,HASH)
        sql="""INSERT INTO recognition.desktop_sessions(operator_id,client_id,local_session_id,model_version_id,
            model_sha256,feature_version,mode,status,started_at,ended_at,termination_reason,neutral_confirmed,
            prediction_count,timing_scope,payload_sha256)
            VALUES (%s,%s,%s,%s,%s,'time-domain-4ch-v1','live','stopped',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,
            'Operator stop',true,10,'processing only',%s) RETURNING id"""
        report=self.c.execute(sql,values).fetchone()[0]
        self.reject(sql,values)
        self.reject("UPDATE recognition.desktop_sessions SET prediction_count=20 WHERE id=%s",(report,))
        self.reject("UPDATE recognition.desktop_sessions SET processing_p95_ms='NaN' WHERE id=%s",(report,))

    def test_provenance_retains_original_coordinates_and_is_immutable(self):
        participant,recording=[uuid.uuid4() for _ in range(2)]
        self.c.execute("INSERT INTO data_protocol.participants(id,pseudonym) VALUES (%s,%s)",(participant,'p_'+participant.hex))
        self.c.execute("INSERT INTO data_protocol.recordings VALUES (%s,%s,1000,10,%s)",(recording,participant,HASH))
        self.c.execute("""INSERT INTO data_protocol.recording_provenance(recording_id,operator_id,source_kind,
            source_name,source_version,source_participant_key,original_signal_key,original_sha256,
            original_start_sample,original_end_sample,channel_map,units,identity_method_version)
            VALUES (%s,%s,'synthetic','fixture','v1','participant-1','signal-1',%s,100,110,'[1,2,3,4]','ADC','fixture-v1')""",
                       (recording,self.operator,HASH))
        self.reject("UPDATE data_protocol.recording_provenance SET original_start_sample=0 WHERE recording_id=%s",(recording,))

    def test_recording_publication_retries_and_conflicts(self):
        participant,recording,local=[uuid.uuid4() for _ in range(3)]
        self.c.execute("INSERT INTO data_protocol.participants(id,pseudonym) VALUES (%s,%s)",(participant,'p_'+participant.hex))
        self.c.execute("INSERT INTO data_protocol.recordings VALUES (%s,%s,1000,10,%s)",(recording,participant,HASH))
        args=(self.operator,self.client,local,recording,HASH)
        a=self.c.execute("SELECT data_protocol.register_client_recording(%s,%s,%s,%s,%s)",args).fetchone()[0]
        b=self.c.execute("SELECT data_protocol.register_client_recording(%s,%s,%s,%s,%s)",args).fetchone()[0]
        self.assertEqual(a,b)
        self.reject("SELECT data_protocol.register_client_recording(%s,%s,%s,%s,%s)",args[:-1]+('b'*64,))

    def test_service_roles_and_reviewer_exclude_credentials(self):
        self.c.execute("SET LOCAL ROLE myocontrol_reviewer")
        self.c.execute("SELECT * FROM ml_experiments.reviewer_results")
        self.reject("SELECT password_hash FROM identity.operators")
        self.reject("SELECT lease_sha256 FROM ml_experiments.experiment_runs")
        self.reject("DELETE FROM ml_experiments.evaluations")
        self.c.execute("RESET ROLE")
        self.c.execute("SET LOCAL ROLE myocontrol_data")
        self.reject("SELECT * FROM identity.operators")
        self.reject("SELECT ml_experiments.interrupt_expired_experiments()")
        self.c.execute("RESET ROLE")

    def test_migration_checksum_tamper_rejected(self):
        spec=importlib.util.spec_from_file_location('test_migrator',ROOT/'services/migrator/migrate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            paths={s:ROOT/'services'/s/'migrations' for s in module.SERVICES}
            copied=Path(d)/'0001_operators.sql'
            copied.write_text((paths['identity']/'0001_operators.sql').read_text(encoding='utf-8')+'\n-- tampered\n',encoding='utf-8')
            paths['identity']=Path(d)
            with self.assertRaisesRegex(RuntimeError,'Applied migration changed'):
                module.apply_migrations(self.c,paths,ROOT/'database/service_roles.sql')


class ConcurrentClaimsTests(unittest.TestCase):
    def test_two_workers_do_not_claim_the_same_job(self):
        dsn=os.environ['TEST_DATABASE_URL']
        operator,client,manifest=[uuid.uuid4() for _ in range(3)]
        with psycopg.connect(dsn) as c:
            if not c.execute('SELECT current_database()').fetchone()[0].startswith('myocontrol_review_'):
                self.fail('Review database required')
            for _ in range(2):
                c.execute("""INSERT INTO ml_experiments.experiment_runs(operator_id,submission_key,kind,family,condition,
                    execution_location,manifest_id,manifest_sha256,feature_contract,input_snapshot,parameters,seed,software_version)
                    VALUES (%s,%s,'source_train','lda','source_only','local_workstation',%s,%s,%s,'{}','{}',1,'concurrency-test')""",
                    (operator,str(uuid.uuid4()),manifest,HASH,Jsonb(CONTRACT)))
        def claim(_):
            with psycopg.connect(dsn) as c:
                return c.execute("SELECT ml_experiments.claim_experiment(%s,%s,%s,'local_workstation')",(operator,client,HASH)).fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(claim,range(2)))
        self.assertTrue(all(ids));self.assertEqual(len(set(ids)),2)
        # Leave explicit immutable failed synthetic runs, not queued/live jobs.
        with psycopg.connect(dsn) as c:
            for k in ids:c.execute("SELECT ml_experiments.finish_experiment(%s,%s,%s,'failed','Synthetic concurrency fixture')",(k,client,HASH))


if __name__ == '__main__':
    unittest.main()
