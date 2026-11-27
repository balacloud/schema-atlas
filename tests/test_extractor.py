"""Run: python -m unittest discover tests   (no database needed)"""
import sys, os, copy, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import extractor as X

S = "LEGACY"
def raw():
    return dict(source="ORA",
      tables=[dict(schema=S, name=n, rows=1, comment="") for n in ["POLICIES", "CUSTOMERS", "CLAIMS", "CLAIM_PAYMENTS"]],
      views=[dict(schema=S, name="V_ACTIVE_POLICIES", comment="")],
      columns=[dict(schema=S, table=t, name=c, type="NUMBER", nullable=True, pos=i) for t, cs in
               {"POLICIES": ["POLICY_NO", "CUST_ID"], "CUSTOMERS": ["CUST_ID"], "CLAIMS": ["CLAIM_NO", "POLICY_NO"],
                "CLAIM_PAYMENTS": ["PAY_ID", "CLAIM_NO"], "V_ACTIVE_POLICIES": ["POLICY_NO"]}.items() for i, c in enumerate(cs)],
      pks=[dict(schema=S, table="POLICIES", cols=["POLICY_NO"]), dict(schema=S, table="CUSTOMERS", cols=["CUST_ID"]),
           dict(schema=S, table="CLAIMS", cols=["CLAIM_NO"]), dict(schema=S, table="CLAIM_PAYMENTS", cols=["PAY_ID"])],
      fks=[],
      sequences=[dict(schema=S, name="SEQ_POLICY_NO"), dict(schema=S, name="SEQ_UNUSED")],
      triggers=[dict(schema=S, name="TRG_POLICIES_BI", table_schema=S, table="POLICIES")],
      deps=[dict(schema=S, name="TRG_POLICIES_BI", type="TRIGGER", r_schema=S, r_name="SEQ_POLICY_NO", r_type="SEQUENCE"),
            dict(schema=S, name="TRG_POLICIES_BI", type="TRIGGER", r_schema=S, r_name="POLICIES", r_type="TABLE"),
            dict(schema=S, name="V_ACTIVE_POLICIES", type="VIEW", r_schema=S, r_name="POLICIES", r_type="TABLE"),
            dict(schema=S, name="PKG_CLAIMS", type="PACKAGE BODY", r_schema=S, r_name="CLAIMS", r_type="TABLE")])

class T(unittest.TestCase):
    def setUp(self): self.m = X.build_model([raw()], []); self.t = {t["name"]: t for t in self.m["tables"]}
    def test_sequence_linked_via_trigger(self):
        self.assertEqual(self.t["POLICIES"]["sequence_details"], [dict(name="SEQ_POLICY_NO", via="trigger TRG_POLICIES_BI")])
    def test_unused_sequence_not_linked(self):
        self.assertTrue(all("SEQ_UNUSED" not in t["sequences"] for t in self.m["tables"]))
    def test_view_is_node_with_dependency_edge(self):
        self.assertEqual(self.t["V_ACTIVE_POLICIES"]["kind"], "view")
        self.assertTrue(any(e["kind"] == "dependency" and e["from"].endswith("V_ACTIVE_POLICIES") and e["to"].endswith("POLICIES") for e in self.m["edges"]))
    def test_dependents_listed(self):
        self.assertIn(dict(type="PACKAGE", name="PKG_CLAIMS"), self.t["CLAIMS"]["dependents"])
    def test_inference_has_reasons(self):
        inf = [e for e in self.m["edges"] if e["kind"] == "inferred"]
        self.assertTrue(inf and all(e["reasons"] and e["confidence"] >= 70 for e in inf))
    def test_views_never_inferred(self):
        self.assertFalse(any(e["kind"] == "inferred" and e["from"].endswith("V_ACTIVE_POLICIES") for e in self.m["edges"]))
    def test_deterministic_regardless_of_input_order(self):
        r2 = copy.deepcopy(raw())
        for k in ("tables", "columns", "deps", "triggers", "sequences"): r2[k].reverse()
        self.assertEqual(self.m["meta"]["fingerprint"], X.build_model([r2], [])["meta"]["fingerprint"])
    def test_no_ai_flag(self): self.assertFalse(self.m["meta"]["ai_used"])
if __name__ == "__main__": unittest.main()
