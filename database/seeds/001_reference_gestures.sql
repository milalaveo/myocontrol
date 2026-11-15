-- Only a canonical rest label is universally required; mappings are protocol-specific.
INSERT INTO myoprosthesis.gestures(code, description)
VALUES ('rest', 'No active gesture')
ON CONFLICT (code) DO NOTHING;
