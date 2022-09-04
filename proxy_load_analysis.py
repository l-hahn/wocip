import requests
from datetime import datetime
from random import choices
from threading import Thread#
from time import sleep

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
    
    min_delta = min(time_delta_values)
    max_delta = max(time_delta_values)
    avg_delta = sum(time_delta_values)/len(time_delta_values)
    err_delta = (thread_count * probe_size) - len(time_delta_values)
    result = (min_delta, avg_delta, max_delta, err_delta)
    return result
    


### INIT GET VALUES ###########################################################
proxies = {
   'http': 'http://rpi-proxy:8080',
   'https': 'http://rpi-proxy:8080'
}

random_links_file = "random_wiki_links.txt"
with open(random_links_file, "r") as file:
    link_list = [
        line.rstrip()
        for line in file
        if len(line.rstrip()) > 0
    ]



### ANALYSIS DONE IN SEVERAL CONFIGS ##########################################
with open("results.txt", "w") as f:
    f.write("proxy\tprobesize\tthreads\tmin(s)\tavg(s)\tmax(s)\terr\n")
    for use_proxy in (False, True):
        for probe_size in (10,25,50,100):
            for thread_count in (1,5,10,20):
                min_delta, avg_delta, max_delta, err_delta = do_test(
                    link_list, probe_size, thread_count, use_proxy
                )
                result_str = (
                    f"avg: {avg_delta}s, min: {min_delta}s, max: {max_delta}s | err: "
                    f"{err_delta}/{probe_size*thread_count} | thrds: {thread_count}, "
                    f"proxy: {use_proxy}, probe_size: {probe_size}"
                )
                print(result_str)
                f.write(
                    f"{use_proxy}\t{probe_size}\t{thread_count}\t{min_delta}"
                    f"\t{avg_delta}\t{max_delta}\t{err_delta}\n"
                )
