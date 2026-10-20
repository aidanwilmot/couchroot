printf '\nTAR VERSION\n'
/usr/bin/tar --version | head -n 2
printf '\nNSS\n'
grep -E '^(passwd|group):' /etc/nsswitch.conf
printf '\nSDK ON DEMAND\n'
ls -ldZ /home/owner/share/tmp/sdk_tools/on-demand
printf '\nMOUNT PROPAGATION\n'
head -n 8 /proc/self/mountinfo
printf '\nVERIFICATION KEY METADATA\n'
ls -lZ /usr/share/sdbd/public.pem
true
