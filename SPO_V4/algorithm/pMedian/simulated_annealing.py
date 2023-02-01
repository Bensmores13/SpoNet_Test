"""
A simulated annealing algorithm for the p-median problem

History
    November 17, 2016
        moved some imports to the __main__ part of the code

Contact:
Ningchuan Xiao
The Ohio State University
Columbus, OH
"""

__author__ = "Ningchuan Xiao <ncxiao@gmail.com>"

import math
import random
from copy import deepcopy
# from teitz_bart import update_assignment
import torch
import numpy as np
# import matplotlib.pyplot as plt
# from plot import display_points_with_pm
import time

INF = float('inf')

def update_assignment(dist, median, d1, d2, p, N):
    """
    Updates d1 and d2 given median so that d1 holds the
    nearest facility for each node and d2 holds the second

    INPUT
      dist:    distance matrix
      median:  list of integers for selected vertices
      d1:      list of nearest facility for each vertex
      d2:      list of second nearest facility
      p:       number of facilities to locate
      N:       number of vertices on the network

    OUTPUT
      dist1:   total distance

      Also will update d1 and d2
    """
    dist1, dist2 = 0.0, 0.0
    node1, node2 = -1, -1
    for i in range(N):
        dist1, dist2 = INF, INF
        for j in range(p):
            if dist[i][median[j]] < dist1:
                dist2 = dist1
                node2 = node1
                dist1 = dist[i][median[j]]
                node1 = median[j]
            elif dist[i][median[j]] < dist2:
                dist2 = dist[i][median[j]]
                node2 = median[j]
        d1[i] = node1
        d2[i] = node2
    dist1 = 0
    for i in range(N):
        dist1 += dist[i][d1[i]]
    return dist1

def evaluate(dist, median, p, N):
    sumdist = 0.0
    for i in range(N):
        dist0 = INF
        for j in range(p):
            if dist[i][median[j]] < dist0:
                dist0 = dist[i][median[j]]
        sumdist += dist0
    return sumdist


# test replacing fr with fi in median without reallocating
# all the nodes
def test_replacement(fi, fr, dist, d1, d2, p, N):
    total = 0.0
    for i in range(N):
        if dist[i][fi] < dist[i][d1[i]]:
            total += dist[i][fi]
        else:
            if fr == d1[i]:
                if dist[i][fi] < dist[i][d2[i]]:
                    total += dist[i][fi]
                else:
                    total += dist[i][d2[i]]
            else:
                total += dist[i][d1[i]]
    return total


def get_new_median(N, p, median):
    samples = []
    for i in range(p):
        s = -1
        while s in median or s in samples:
            s = random.sample(range(N), 1)[0]
        samples.append(s)
    return samples


def bestRandomNeighbor(median, dist, N, p):
    candidates = []
    r_mins = []
    for j in range(p):
        candidates.append(get_new_median(N, p, median))
        r_mins.append(evaluate(dist, candidates[j], p, N))
    r_min = INF
    i_min = -1
    for j in range(p):
        if r_mins[j] < r_min:
            r_min = r_mins[j]
            i_min = j
    return r_min, candidates[i_min]


def bestGeoNeighbor(median, dist, d1, d2, N, p, dthreshold):
    r_min = INF
    fi = None
    fr = None
    for j in range(p):
        r_min_temp = INF
        fi_temp = -1
        for i in range(N):  # try replacing j with an i
            if dist[median[j]][i] > dthreshold or i in median:
                continue
            if random.random() > 0.67:
                continue
            r1 = test_replacement(i, median[j], dist, d1, d2, p, N)
            if r1 < r_min_temp:
                r_min_temp = r1
                fi_temp = i
        if r_min_temp < r_min:
            r_min = r_min_temp
            fi = fi_temp
            fr = j
    return r_min, fi, fr


def next(r, T, median, dist, d1, d2, p, N, dthreshold, neighbormethod):
    r1 = r
    if neighbormethod == 0:
        r_min, fi, fr = bestGeoNeighbor(median, dist, d1, d2, N, p, dthreshold)
        test = acceptable(10 * (r_min - r) / r, T)
        if test[0] > 0:
            median[fr] = fi
            r1 = update_assignment(dist, median, d1, d2, p, N)
        return test[0], r1, median
    else:
        r_min, candidate = bestRandomNeighbor(median, dist, N, p)
        test = acceptable(10 * (r_min - r) / r, T)
        if test[0] > 0:
            median = candidate
            r1 = update_assignment(dist, median, d1, d2, p, N)
        return test[0], r1, median


def acceptable(delta, T):
    if delta < 0:  # better solution
        return 1, 1
    if delta == 0:  # same solution, no change
        return 0, 0
    prob = math.exp(-delta / T)
    if random.random() < prob:  # worse solution, accept
        return 2, prob
    return 0, prob  # worse solution, reject


def simulated_annealing(dist, p, neighbormethod=0, verbose=False):
    N = len(dist)
    dmax = max([max(dist[i]) for i in range(N)])
    dthreshold = dmax / 2
    d1 = [-1 for i in range(N)]
    d2 = [-1 for i in range(N)]

    ## Initialization
    median = random.sample(range(N), p)
    r = update_assignment(dist, median, d1, d2, p, N)
    first = [deepcopy(r), deepcopy(median)]
    best = [r, median]
    if verbose:
        print(first[0])

    accepted_same = 0
    T = 100.0
    while True:
        result = next(r, T, median, dist, d1, d2, p, N,
                      dthreshold, neighbormethod)
        if result[0] > 0:
            r = result[1]
            if r < best[0]:
                best = [r, deepcopy(result[2])]
                accepted_same = 0
            if result[0] == 2:
                accepted_same += 1
            if r == best[0] and accepted_same > 2:
                break
            T = 0.9 * T
            if verbose:
                print(r)
                if result[0] == 2:
                    print('*', )
                print(median)
        else:
            break
    return first, best


if __name__ == "__main__":
    num_sample = 1
    n = 1000
    p = 15
    torch.manual_seed(1234)
    datas = []
    dists = []
    centers = []
    objs = []
    for i in range(num_sample):
        data = torch.FloatTensor(n, 2).uniform_(0, 1)
        dist = (data[None, :, :] - data[:, None, :]).norm(p=2, dim=-1)
        datas.append(data)
        dists.append(dist)
    start_time = time.time()
    for i in range(num_sample):
        points = datas[i]
        dist = dists[i]
        np_dist = np.array(dist)
        re = simulated_annealing(np_dist, p, verbose=False)
        result = re[1]
        objs.append(result[0])
        # centers.append(result[1])
    end_time = time.time() - start_time
    average_obj = np.mean(objs)
    print(f"The number of instances is: {num_sample}")
    print(f"The total solution time is: {end_time}")
    print(f"The average solution time is: {end_time/num_sample}")
    print(f"The average objective is: {average_obj}")
    # n = 20
    # p = 4
    # points = torch.FloatTensor(n, 2).uniform_(0, 1)
    # dist = (points[None, :, :] - points[:, None, :]).norm(p=2, dim=-1)
    # np_dist = np.array(dist)
    #
    # re = simulated_annealing(np_dist, p, verbose=True)
    # result = re[1]
    # centers = torch.tensor(result[1], dtype=torch.int32)
    # obj = result[0]
    #
    # fig = plt.figure(figsize=(8,8))
    # plt.title(f'The result of P-median by SA\nThe objective distance: {obj}')
    # display_points_with_pm(points, centers)
    # print("The objective of SA is ", obj)
    # plt.show()
