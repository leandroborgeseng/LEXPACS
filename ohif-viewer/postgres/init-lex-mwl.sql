-- E13: fila MWL sincronizada a partir do SQL hospitalar (dev)
CREATE TABLE IF NOT EXISTS lex_mwl_schedule (
    id SERIAL PRIMARY KEY,
    accession_number VARCHAR(32) NOT NULL UNIQUE,
    patient_id VARCHAR(64) NOT NULL,
    patient_name VARCHAR(128) NOT NULL,
    modality VARCHAR(16) NOT NULL,
    station_aet VARCHAR(16) NOT NULL,
    procedure_description VARCHAR(128) NOT NULL DEFAULT '',
    scheduled_date DATE NOT NULL DEFAULT CURRENT_DATE
);

INSERT INTO lex_mwl_schedule (
    accession_number, patient_id, patient_name, modality, station_aet, procedure_description, scheduled_date
) VALUES
    ('LEXMWL001', 'MWLTEST01', 'Paciente^MWL Teste', 'DX', 'RX_SALA1', 'Raio-X sala 1', CURRENT_DATE),
    ('LEXMWL002', 'MWLTEST02', 'Paciente^MWL CT', 'CT', 'CT_SALA1', 'Tomografia', CURRENT_DATE)
ON CONFLICT (accession_number) DO NOTHING;
