CREATE VIEW myoprosthesis.reviewer_metrics AS
SELECT e.evaluation_id, e.participant_id, e.model_id, e.manifest_id, e.feature_config_id,
       m.metric, m.value, m.missing_reason
FROM myoprosthesis.completed_evaluations e
JOIN myoprosthesis.evaluation_metrics m ON m.evaluation_id = e.evaluation_id;
