from app.services.validate import validate_rows

def test_malformed_tiny_value_gets_flagged():
    rows=[]
    for cat,val in [("A",500000),("B",200000),("C",300000),("D",100000),("Spam",5)]:
        rows.append({"platform":"Instagram","policy_category":cat,"content_actioned_raw":"5." if cat=="Spam" else str(val),"content_actioned_numeric":val,"proactive_rate":0.9,"month":"Jun-2021","period_end":"2021-06-15"})
    out, issues=validate_rows(rows)
    spam=[r for r in out if r["policy_category"]=="Spam"][0]
    assert spam["validation_status"]=="review"
    assert issues
