set -e
C=guard_test
docker rm -f $C >/dev/null 2>&1 || true
docker run -d --name $C -p 55433:5432 -e POSTGRES_PASSWORD=x -e POSTGRES_USER=meridian -e POSTGRES_DB=meridian postgres:16-alpine >/dev/null
for i in $(seq 1 40); do docker exec $C pg_isready -U meridian -q && break; sleep 1; done
docker exec -i $C psql -U meridian -d meridian -q <<'SQL'
CREATE TABLE market_snapshots(market_slug text, game_id text, captured_at timestamptz,
  best_bid numeric, best_ask numeric, is_live boolean);
-- frzn: STREAMING every 30s but price NEVER changes  = the 2026-09-05 venue freeze
INSERT INTO market_snapshots SELECT 'asc-frzn-m'||i,'g'||i,
  now()-interval '25 min'+(n*interval '30 sec'),0.50,0.52,true
FROM generate_series(1,12) i, generate_series(0,48) n;
-- good: streaming every 30s, price moves
INSERT INTO market_snapshots SELECT 'asc-good-m'||i,'g'||i,
  now()-interval '25 min'+(n*interval '30 sec'),0.50+n*0.01,0.52+n*0.01,true
FROM generate_series(1,12) i, generate_series(0,48) n;
-- dead: is_live STILL TRUE but stream died — two rows 23 min apart (gap > 600s)
INSERT INTO market_snapshots SELECT 'asc-dead-m'||i,'g'||i,
  now()-interval '25 min'+(n*interval '23 min'),0.50,0.52,true
FROM generate_series(1,12) i, generate_series(0,1) n;
-- mix: 6 live streaming movers + 6 dead streams in ONE league
INSERT INTO market_snapshots SELECT 'asc-mix-m'||i,'g'||i,
  now()-interval '25 min'+(n*interval '30 sec'),0.50+n*0.01,0.52+n*0.01,true
FROM generate_series(1,12) i, generate_series(0,48) n;
INSERT INTO market_snapshots SELECT 'asc-mix-d'||i,'g'||i,
  now()-interval '25 min'+(n*interval '23 min'),0.50,0.52,true
FROM generate_series(1,6) i, generate_series(0,1) n;
INSERT INTO market_snapshots SELECT 'asc-thin-m'||i,'g'||i,
  now()-interval '25 min'+(n*interval '30 sec'),0.50+n*0.01,0.52+n*0.01,true
FROM generate_series(1,6) i, generate_series(0,48) n;
INSERT INTO market_snapshots SELECT 'asc-thin-d'||i,'g'||i,
  now()-interval '25 min'+(n*interval '23 min'),0.50,0.52,true
FROM generate_series(1,6) i, generate_series(0,1) n;
SQL
echo "===== alarm_v5.SQL, verbatim, against planted data ====="
/Users/yayardia/Documents/Quant/Meridian/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'/Users/yayardia/Documents/Quant/Meridian/scripts')
import alarm_v5 as a, psycopg
conn=psycopg.connect("postgresql://meridian:x@localhost:55433/meridian")
cur=conn.cursor(); cur.execute(a.SQL, {"win":a.WINDOW_MIN,"stream_gap":a.STREAM_GAP_S})
rows={r[0]:r for r in cur.fetchall()}
exp={"frzn":(12,0.0,"ALARM"),"good":(12,100.0,"OK"),"mix":(12,100.0,"OK"),"thin":(6,100.0,"INSUFFICIENT")}
fails=0
for lg,(mk,pct,verdict) in exp.items():
    if lg not in rows: print(f"  **FAIL** {lg}: no row returned"); fails+=1; continue
    r=rows[lg]; got_mk,got_pct=int(r[1]),float(r[3])
    v,_=a.classify(a.LeagueRow(lg,got_mk,int(r[2]),got_pct,int(r[5]),float(r[6] or 0),float(r[7] or 30)))
    ok = got_mk==mk and abs(got_pct-pct)<0.05 and v==verdict
    fails += not ok
    print(f"  {'PASS' if ok else '**FAIL**'} {lg:5s} markets={got_mk:2d}(exp {mk}) pct={got_pct:5.1f}(exp {pct}) -> {v} (exp {verdict})")
print(f"  {'PASS' if 'dead' not in rows else '**FAIL**'} dead  league absent entirely (every row dropped by the 600s guard)")
fails += 'dead' in rows
print("\n"+("GUARD TEST PASSED" if not fails else f"{fails} FAILURE(S)"))
PY
docker rm -f $C >/dev/null
