/system script
add name=rf-update-dns-adlist policy=read,write,test source={
    :local url "https://raw.githubusercontent.com/sip-it/build_rsc/release/dns/category-ads-all.txt"
    :log info ("rf-update-dns-adlist: ensuring adlist url " . $url)
    :if ([:len [/ip dns adlist find where url=$url]] = 0) do={
        /ip dns adlist add url=$url ssl-verify=no
        :delay 2s
    }
    :do {
        /ip dns adlist reload
        :log info "rf-update-dns-adlist: reload done"
    } on-error={
        :log error ("rf-update-dns-adlist: failed: " . $message)
    }
}
