import unittest

from app.hl7_orm import parse_orm_message, unwrap_mllp, wrap_mllp

SAMPLE_ORM = """MSH|^~\\&|RIS|CLINICA|LEXPACS|LEX|20260621143000||ORM^O01|ORM00001|P|2.5\r
PID|1||HL7TEST01^^^CLINIC||SILVA^MARIA||19800115|F\r
ORC|NW|PLACER001|ACC_E18_TEST|||||||20260621143000\r
OBR|1|PLACER001|ACC_E18_TEST|CTCHEST^TC TORAX|||||||||20260621143000||||||||CT|20260621143000||||F\r"""


class Hl7OrmParserTest(unittest.TestCase):
    def test_parse_orm_new_order(self) -> None:
        parsed = parse_orm_message(SAMPLE_ORM)
        self.assertEqual(parsed.order_control, "NW")
        self.assertEqual(parsed.accession_number, "ACC_E18_TEST")
        self.assertEqual(parsed.patient_id, "HL7TEST01")
        self.assertEqual(parsed.modality, "CT")
        self.assertFalse(parsed.is_cancel)

    def test_mllp_wrap_unwrap(self) -> None:
        frame = wrap_mllp(SAMPLE_ORM)
        self.assertTrue(frame.startswith(b"\x0b"))
        self.assertTrue(frame.endswith(b"\x1c\x0d"))
        self.assertIn("ORM^O01", unwrap_mllp(frame))


if __name__ == "__main__":
    unittest.main()
