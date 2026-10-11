using System;using System.Runtime.InteropServices;
class Control {
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key,out int value);
 [DllImport("libvconf.so.0")] static extern int vconf_set_int(string key,int value);
 static int Main(){const string k="memory/appfw/app_context_db_change";int previous,actual;if(vconf_get_int(k,out previous)!=0)return 1;int next=previous==0?1:0;if(vconf_set_int(k,next)!=0||vconf_get_int(k,out actual)!=0||actual!=next)return 2;Console.WriteLine("Native context reload notification accepted; allow six seconds");return 0;}
}
