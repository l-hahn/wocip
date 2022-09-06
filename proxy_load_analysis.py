import requests
from datetime import datetime
from random import choices
from threading import Thread#
from time import sleep
from math import sqrt

def do_request(url_list, count, time_delta, use_proxy=True):
    global proxies
    for url in choices(url_list, k=count):
        kwargs = {'url':url,'proxies':proxies} if use_proxy else {'url':url}
        start = datetime.now()
        try:
            response = requests.get(**kwargs)
        except Exception as e:
            print("Some error ...", e)
            time_delta.append(-1)
            continue
        time_diff = datetime.now() - start
        if response.status_code in (200, '200'):
            time_delta.append(time_diff)
        else:
            time_delta.append(-1)
            print(f"WARNING for URL '{url}'")

def do_analysis(url_list, probe_size, thread_count, use_proxy=True):
    thread_timedeltas = [
        []
        for _ in range(thread_count)
    ]
    
    threads = [
        Thread(target=do_request, args=(
            url_list, probe_size, time_delta, use_proxy
        ))
        for time_delta in thread_timedeltas
    ]
    for thread in threads:
        thread.start()
    
    wait_string = "-\|/"
    ctr = 0
    while any(
        thread.is_alive()
        for thread in threads
    ):
        print(f"Threads are still execution ... {wait_string[ctr%4]}\r", end="")
        ctr += 1
        sleep(0.5)
    print("Finished!", " "*100)

    for idx in range(len(threads)-1,-1,-1):
        del threads[idx]
    del threads
    
    return thread_timedeltas


def do_test(url_list, probe_size, thread_count, use_proxy):
    thread_timedeltas = do_analysis(url_list, probe_size, thread_count, use_proxy)
    time_deltas = [
        [
            time.total_seconds()
            for time in time_delta
            if time != -1
        ]
        for time_delta in thread_timedeltas
    ]
    time_delta_values = [val for vals in time_deltas for val in vals]
    ctr_deltas = len(time_delta_values)    
    min_delta = min(time_delta_values)
    max_delta = max(time_delta_values)
    avg_delta = sum(time_delta_values)/ctr_deltas
    err_delta = (thread_count * probe_size) - ctr_deltas
    std_delta = sqrt(sum( (delta-avg_delta)**2 for delta in time_delta_values)/(ctr_deltas-1))
    sort_delta = sorted(time_delta_values)
    med_delta = sort_delta[(ctr_deltas-1)//2]
    if len(time_delta_values) % 2 == 0:
        med_delta = (med_delta + sort_delta[(ctr_deltas)//2])/2

    result = (min_delta, med_delta, avg_delta, max_delta, std_delta, err_delta)
    return result
    


### INIT GET VALUES ###########################################################
proxy_file_mappings = {
    "rpi-proxy-4": "rpi-4",
    "rpi-proxy-2": "rpi-2",
    "rpi-proxy-0": "rpi-0",
    "rpi-proxy-pico": "rpi-pico"
}


random_links_file = "random_wiki_links.txt"
with open(random_links_file, "r") as file:
    link_list = [
        line.rstrip()
        for line in file
        if len(line.rstrip()) > 0
    ]

allfile = open("results_rpi-proxies.txt","w")
allfile.write("rpi\tproxy\tprobesize\tthreads\tmin(s)\tmed(s)\tavg(s)\tmax(s)\tsd(s)\terr\n")
### ANALYSIS DONE IN SEVERAL CONFIGS ##########################################
for proxy,filename in proxy_file_mappings.items():
    proxies = {
        'http': f'http://{proxy}:8080',
        'https': f'http://{proxy}:8080'
    }
    with open(f"results_{filename}-proxy.txt", "w") as f:
        #f.write("proxy\tprobesize\tthreads\tmin(s)\tmed(s)\tavg(s)\tmax(s)\tsd(s)\terr\n")
        for use_proxy in (False, True):
            for probe_size in (10,25,50,100):
                for thread_count in (1,5,10,20):
                    min_delta, med_delta, avg_delta, max_delta, std_delta, err_delta = do_test(
                        link_list, probe_size, thread_count, use_proxy
                    )
                    data_str = (
                        f"{use_proxy}\t{probe_size}\t{thread_count}\t{min_delta}\t{med_delta}"
                        f"\t{avg_delta}\t{max_delta}\t{std_delta}\t{err_delta}\n"
                    )
                    result_str = (
                        f"avg: {avg_delta}s, med:{med_delta} min: {min_delta}s, max: {max_delta}s, "
                        f"std: {std_delta}s | err: {err_delta}/{probe_size*thread_count} | "
                        f"thrds: {thread_count}, proxy: {use_proxy}, probe_size: {probe_size}, "
                        f"rpi: {filename}"
                    )
                    print(result_str)

                    f.write(data_str)
                    allfile.write(
                        f"{filename}\t{data_str}"
                    )
allfile.close()
