import unittest

from app.hl7_orm import parse_orm_message, unwrap_mllp, wrap_mllp

def _obr(fields: dict[int, str]) -> str:
    """Monta um OBR pelo número do campo HL7 v2.5 (OBR-1 = índice 1), evitando erro de contagem de pipes."""
    last = max(fields)
    return "|".join(["OBR"] + [fields.get(i, "") for i in range(1, last + 1)])


# OBR-7 = data/hora observação (agenda), OBR-22 = data do resultado,
# OBR-24 = Diagnostic Serv Sect ID (modalidade), OBR-25 = status do resultado.
SAMPLE_OBR = _obr(
    {
        1: "1",
        2: "PLACER001",
        3: "ACC_E18_TEST",
        4: "CTCHEST^TC TORAX",
        7: "20260621143000",
        22: "20260621143000",
        24: "CT",
        25: "F",
    }
)

SAMPLE_ORM = (
    "MSH|^~\\&|RIS|CLINICA|LEXPACS|LEX|20260621143000||ORM^O01|ORM00001|P|2.5\r"
    "PID|1||HL7TEST01^^^CLINIC||SILVA^MARIA||19800115|F\r"
    "ORC|NW|PLACER001|ACC_E18_TEST|||||||20260621143000\r"
    f"{SAMPLE_OBR}\r"
)


class Hl7OrmParserTest(unittest.TestCase):
    def test_parse_orm_new_order(self) -> None:
        parsed = parse_orm_message(SAMPLE_ORM)
        self.assertEqual(parsed.order_control, "NW")
        self.assertEqual(parsed.accession_number, "ACC_E18_TEST")
        self.assertEqual(parsed.patient_id, "HL7TEST01")
        self.assertEqual(parsed.modality, "CT")
        self.assertFalse(parsed.is_cancel)
        self.assertEqual(parsed.scheduled_date.isoformat(), "2026-06-21")

    def test_obr24_vazio_usa_codigo_de_modalidade_do_obr4(self) -> None:
        raw = SAMPLE_ORM.replace(SAMPLE_OBR, _obr({1: "1", 3: "ACC2", 4: "MR^RM CRANIO"}))
        self.assertEqual(parse_orm_message(raw).modality, "MR")

    def test_sem_modalidade_cai_em_ot(self) -> None:
        raw = SAMPLE_ORM.replace(SAMPLE_OBR, _obr({1: "1", 3: "ACC3", 4: "CTCHEST^TC TORAX"}))
        self.assertEqual(parse_orm_message(raw).modality, "OT")

    def test_mllp_wrap_unwrap(self) -> None:
        frame = wrap_mllp(SAMPLE_ORM)
        self.assertTrue(frame.startswith(b"\x0b"))
        self.assertTrue(frame.endswith(b"\x1c\x0d"))
        self.assertIn("ORM^O01", unwrap_mllp(frame))


if __name__ == "__main__":
    unittest.main()
