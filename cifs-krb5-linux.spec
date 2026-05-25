Name:           cifs-krb5-linux
Version:        1.0
Release:        1%{?dist}
Summary:        Automated Kerberos-authenticated CIFS mounts
Source0:        %{name}-%{version}.tgz

License:        MIT
URL:            https://github.com/aj3t4m/cifs-krb5-linux

BuildArch:      noarch

Requires:       cifs-utils
Requires:       krb5-workstation
Requires:       sssd-kcm

%description
Automated Kerberos-authenticated CIFS (SMB) mounts using per-share
configuration files, a systemd generator, and a custom SPNEGO upcall router.

At boot the systemd generator reads /etc/cifs-mounts.d/*.conf and produces
per-share units that obtain a Kerberos ticket from a keytab, mount the share,
and keep the ticket alive via a renewal timer.

The upcall router intercepts kernel Kerberos upcalls and directs each one to
the correct credential cache, allowing multiple shares on the same server to
use different Kerberos principals.

%prep
%setup -q

%install
install -D -m 0755 %{_builddir}/%{name}-%{version}/usr/lib/systemd/system-generators/cifs-krb5-generator \
    %{buildroot}%{_prefix}/lib/systemd/system-generators/cifs-krb5-generator

install -D -m 0755 %{_builddir}/%{name}-%{version}/usr/local/sbin/cifs-upcall-router \
    %{buildroot}/usr/sbin/cifs-upcall-router

install -D -m 0755 %{_builddir}/%{name}-%{version}/etc/security/keytabs/create-keytab \
    %{buildroot}%{_sysconfdir}/security/keytabs/create-keytab

install -d -m 0750 %{buildroot}%{_sysconfdir}/cifs-mounts.d

# Doc files
install -D -m 0644 %{_builddir}/%{name}-%{version}/README.md \
    %{buildroot}%{_docdir}/%{name}/README.md

install -D -m 0644 %{_builddir}/%{name}-%{version}/LICENSE \
    %{buildroot}%{_docdir}/%{name}/LICENSE

install -D -m 0644 %{_builddir}/%{name}-%{version}/etc/cifs-mounts.d/share1.conf \
    %{buildroot}%{_docdir}/%{name}/examples/share1.conf

install -D -m 0644 %{_builddir}/%{name}-%{version}/etc/cifs-mounts.d/share2.conf \
    %{buildroot}%{_docdir}/%{name}/examples/share2.conf

%files
%license %{_docdir}/%{name}/LICENSE
%doc %{_docdir}/%{name}/README.md
%doc %{_docdir}/%{name}/examples/

%dir %attr(0750, root, root) %{_sysconfdir}/cifs-mounts.d
%dir %attr(0750, root, root) %{_sysconfdir}/security/keytabs

%attr(0755, root, root) %{_prefix}/lib/systemd/system-generators/cifs-krb5-generator
%attr(0755, root, root) /usr/sbin/cifs-upcall-router
%attr(0755, root, root) %{_sysconfdir}/security/keytabs/create-keytab

%post
# Replace the cifs.upcall handler with the router
sed -i 's|/usr/sbin/cifs.upcall|/usr/sbin/cifs-upcall-router|g' \
    %{_sysconfdir}/request-key.d/cifs.spnego.conf
systemctl daemon-reload 2>/dev/null || true

%preun
# Restore the original cifs.upcall handler
if [ $1 -eq 0 ]; then
    sed -i 's|/usr/sbin/cifs-upcall-router|/usr/sbin/cifs.upcall|g' \
        %{_sysconfdir}/request-key.d/cifs.spnego.conf
    for conf in %{_sysconfdir}/cifs-mounts.d/*.conf; do
        [ -f "$conf" ] || continue
        MOUNT="$(awk -F= '/^[[:space:]]*MOUNT[[:space:]]*=/ {
            val=$2; sub(/^[[:space:]]+/,"",val); sub(/[[:space:]]+$/,"",val)
            gsub(/^["\x27]|["\x27]$/,"",val); print val; exit }' "$conf")"
        [ -n "$MOUNT" ] || continue
        name="$(systemd-escape -p "$MOUNT")"
        mount_unit="$(systemd-escape -p --suffix=mount "$MOUNT")"
        systemctl stop "cifs-renew-${name}.timer" 2>/dev/null || true
        systemctl stop "cifs-renew-${name}.service" 2>/dev/null || true
        systemctl stop "cifs-kinit-${name}.service" 2>/dev/null || true
        systemctl stop "$mount_unit" 2>/dev/null || true
    done
fi

%postun
systemctl daemon-reload 2>/dev/null || true

%changelog
* Sun May 25 2026 Tomasz Mateja <aj3t4m@gmail.com> - 1.0-1
- Initial release
