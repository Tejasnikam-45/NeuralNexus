import time
import json
import csv
import argparse
import urllib.request
import urllib.error

def main():
    parser = argparse.ArgumentParser(description="Replay UPI transactions for NeuralNexus testing.")
    parser.add_argument("--csv", type=str, default="data/upi_transactions.csv", help="Path to CSV file")
    parser.add_argument("--limit", type=int, default=500, help="Max transactions to replay")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between requests in seconds")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000/score", help="API Endpoint")
    args = parser.parse_args()

    print(f"[*] Replaying from {args.csv}...")
    print(f"[*] Target: {args.url}")
    print(f"[*] Limit: {args.limit}, Delay: {args.delay}s\n")

    count = 0
    blocked = 0
    approved = 0
    mfa = 0

    try:
        with open(args.csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if count >= args.limit:
                    break
                
                # Mapped payload including behavioral risk features from the CSV
                payload = {
                    "transaction_id": row.get("transaction_id", f"txn_{count}"),
                    "user_id": row.get("user_upi_id", f"usr_{count}"),
                    "session_id": "",
                    "amount_usd": float(row.get("amount_inr", 100)) / 83.0,
                    "merchant_id": row.get("receiver_upi_id", "merchant_01"),
                    "merchant_category_encoded": 0,
                    "ip_address": "8.8.8.8" if row.get("login_new_ip") == "1" else "192.168.1.1",
                    "device_id": "new_unrecognized_dev" if row.get("login_new_device") == "1" else f"known_dev_{count%10}",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "hour_of_day": 3 if row.get("is_fraud") == "1" else 12, # Night time for fraud
                    "day_of_week": 3,
                    "is_new_merchant": row.get("is_fraud") == "1",
                    "ip_country_code_changed": row.get("login_new_ip") == "1",
                    "timestamp_utc": time.time()
                }

                req = urllib.request.Request(args.url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
                try:
                    with urllib.request.urlopen(req) as resp:
                        res = json.loads(resp.read().decode())
                        decision = res.get("decision", "approve")
                        score = res.get("score", 0)
                        
                        color = "\033[92m" if decision == "approve" else "\033[93m" if decision == "mfa" else "\033[91m"
                        print(f"[{count+1:03d}] {payload['user_id']} -> {payload['merchant_id']} | ${payload['amount_usd']:.2f} | Score: {score:.1f} | Decision: {color}{decision.upper()}\033[0m")
                        
                        if decision == "block": blocked += 1
                        elif decision == "mfa": mfa += 1
                        else: approved += 1
                        
                except Exception as e:
                    print(f"[-] API Error for txn {count}: {e}")
                
                count += 1
                time.sleep(args.delay)
                
    except FileNotFoundError:
        print(f"[!] Error: Could not find '{args.csv}'. Ensure you are running from the NeuralNexus root folder.")
        
    print(f"\n[+] Replay complete. Processed {count} transactions.")
    print(f"    Approved: {approved} | Blocked: {blocked} | MFA: {mfa}")

if __name__ == "__main__":
    main()
