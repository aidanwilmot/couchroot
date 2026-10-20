BEGIN IMMEDIATE;
CREATE TEMP TABLE hub_guard(ok INTEGER CHECK(ok=1));
INSERT INTO hub_guard SELECT count(*)=1 FROM task_filter WHERE appid='MiniHub001.Hub' AND source_selector='package:NRi6kdBYJ0.AirPlayWebApp,~context:standby,vconf:(ready=memory/menu/network/airplay_status)' AND source_event='pause' AND request='launch' AND target_selector='package:MiniHub001.Hub' AND target IS NULL AND args IS NULL;
INSERT INTO hub_guard SELECT count(*)=1 FROM task_filter WHERE appid='MiniHub001.Hub';
INSERT INTO task_filter (appid,source_selector,source_event,request,target_selector,target,args) VALUES ('MiniHub001.Hub','package:com.samsung.tv.airplay-app,~context:standby,vconf:(ready=memory/menu/network/airplay_status)','deactivate','launch','package:MiniHub001.Hub',NULL,NULL);
DROP TABLE hub_guard;
COMMIT;
