BEGIN IMMEDIATE;
CREATE TEMP TABLE hub_guard (ok INTEGER CHECK(ok=1));
INSERT INTO hub_guard SELECT count(*)=1 FROM managed_app WHERE appid='MiniHub001.Hub' AND ui_type IS NULL AND source IS NULL;
INSERT INTO hub_guard SELECT count(*)=0 FROM task_filter WHERE appid='MiniHub001.Hub';
INSERT INTO task_filter (appid,source_selector,source_event,request,target_selector,target,args) VALUES ('MiniHub001.Hub','package:NRi6kdBYJ0.AirPlayWebApp,~context:standby,vconf:(ready=memory/menu/network/airplay_status)','pause','launch','package:MiniHub001.Hub',NULL,NULL);
DROP TABLE hub_guard;
COMMIT;
