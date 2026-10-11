set -eu
sha256sum -c <<'HASHES'
5426f8a156a10f7900af1dd1d16f5e733d3378e98055b53e4b28ad59a497473d  /usr/lib/systemd/system/sdbd.service
224cf12e14dcfe0e99198b50536d0a38543f4ef8d77184c5c77f87c584408500  /usr/lib/systemd/system/sdbd.service.d/exec.conf
ee82546d1fc4d81506ef04abfd6a2ea0463c9efd983587c77f72fb3b138d5acb  /usr/lib/systemd/system/sdbd.service.d/restart-on-fail.conf
90cb4b09782d55b12dc6e11fefd017273103a9349b034d4802c3d09a03b9b20a  /usr/lib/systemd/system/sdbd_tcp.socket
b283210ce68b957db244c0c8871b3df46d9b844d070ac72fcbc7a1a7c613cb27  /usr/lib/systemd/system/sdbd_tcp.socket.d/store-develop-mode-release.conf
b6829f0f7e95464178f92922e5fdca83bf0874df2e1bbb77d68db6892a5490b3  /usr/lib/systemd/system/AT-HUB.service
c6369e7dec69408e176daa252d436acf6f8e265f560504d8bd831c8023c71d61  /opt/etc/parseinfo.sh
2ac5be9ff82ffa223e5b359f1c56ec2c69acbaaba3b8155a1c6719a950c2d46f  /opt/etc/get_top_process.sh
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  /home/owner/apps_rw/com.samsung.tv.store/data/develop_mode
e5840c05c567183295f0bb37e3b28613618cec5e0c8c08a44a400672a1c73310  /usr/bin/dotnet
607e2991160449c0e5fb3acbdef1e47ac761086e5ad8942fff8a9725633ae20e  /usr/sbin/sdbd-tarlauncher
154b98168c7c6e7d2ab358fa69c6ac6fca6a13b3931fbbb8fb106655f3547a0d  /etc/passwd
c83cab64331f092ba99f666b8bb20a49dd1fff04030336c2ea34f6b55ca09d09  /usr/share/sdbd/public.pem
HASHES
ls -lZ /home/owner/apps_rw/com.samsung.tv.store/data/develop_mode
getcap /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher
systemctl --failed --no-pager
ps -eo pid,uid,comm | grep -E "csfs|home|remote|webapp|sdb"
ls -la /home/owner/share/tmp/sdk_tools
