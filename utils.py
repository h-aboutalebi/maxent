# This is the utility file for all experiments. 
# It contains:
# 1) definition of all command line arguments
# 2) functions for determining policy weights

import cvxpy as cvx
import numpy as np
import scipy.stats

import argparse
import copy
import sys
import os

np.set_printoptions(precision=15)

parser = argparse.ArgumentParser(description='Ant Entropy')

# learning and Frank Wolfe args
parser.add_argument('--gamma', type=float, default=0.99, metavar='g',
                    help='learning rate')
parser.add_argument('--lr', type=float, default=1e-3, metavar='lr',
                    help='learning rate')
parser.add_argument('--eps', type=float, default=0.05, metavar='eps',
                    help='exploration rate')
parser.add_argument('--episodes', type=int, default=16, metavar='ep',
                    help='number of episodes per agent')
parser.add_argument('--epochs', type=int, default=16, metavar='epo',
                    help='number of models to train on entropy rewards')
parser.add_argument('--T', type=int, default=10000, metavar='T',
                    help='number of steps to roll out entropy policy')
parser.add_argument('--T_small', type=int, default=1000, metavar='T',
                    help='small number of steps to roll out entropy policy')
parser.add_argument('--n', type=int, default=20, metavar='n',
                    help='number of rollouts to average over')
parser.add_argument('--env', type=str, default='test', metavar='env',
                    help='the env to learn')


# policy architecture args
parser.add_argument('--hid', type=int, default=300)
parser.add_argument('--l', type=int, default=2)
parser.add_argument('--seed', '-s', type=int, default=-1)
parser.add_argument('--exp_name', type=str, default='test')

# saving args
parser.add_argument('--models_dir', type=str, default='logs/file.out', metavar='N',
                    help='directory from which to load model policies')
parser.add_argument('--save_models', action='store_true',
                    help='collect a video of the final policy')
parser.add_argument('--render', action='store_true',
                    help='render the environment')
parser.add_argument('--record_steps', type=int, default=5000, metavar='rs',
                    help='number of steps for each video recording')

# Gaussian reduction args -- for Ant
parser.add_argument('--gaussian', action='store_true',
                    help='use random Gaussian to reduce state')
parser.add_argument('--reduce_dim', type=int, default=5, metavar='rd',
                    help='dimension of Gaussian')

# run config
parser.add_argument('--start_steps', type=int, default=10000, metavar='ss',
                    help='start steps parameter')
parser.add_argument('--avg_N', type=int, default=1, metavar='aN',
                    help='unique states visited average runs')

# experimental args
parser.add_argument('--deterministic', action='store_true',
                    help='act deterministically in mixed policy')
parser.add_argument('--cumulative', action='store_true',
                    help='use cumulative reward_fn')
parser.add_argument('--grad_ent', action='store_true',
                    help='use original gradient of entropy rewards')
parser.add_argument('--initial_state', action='store_true',
                    help='seed learning policies with initial state')

# weighting arguments
parser.add_argument('--geometric', action='store_true',
                    help='use geometric sequence to weight policies')
parser.add_argument('--fully_corrective', action='store_true',
                    help='use fully corrective weighting to weight policies')

args = parser.parse_args()


if args.geometric and args.fully_corrective:
    raise ValueError("must set only one: --fully_corrective  --geometric")
if args.T_small > args.T:
    raise ValueError('T_small > T: behavior will not be correct')

def get_args():
    return copy.deepcopy(args)

if not os.path.exists('logs/encoded'):
    os.makedirs('logs/encoded')

logfile = 'logs/' + args.exp_name + '.txt'
def log_statement(s):
    print(s)
    with open(logfile, 'a') as f:
        f.write(str(s)+'\n')

# Project the vector y onto the unit simplex.
def proj_unit_simplex(y):
    '''
    Returns the point in the simplex a^Tx = 1, x&amp;amp;amp;amp;gt;=0 that is
     closest to y (according to Euclidian distance)
    '''
    d = len(y)
    a = np.ones(d)
    # setup the objective and constraints and solve the problem
    x = cvx.Variable(d)
    obj = cvx.Minimize(cvx.sum_squares(x - y))
    constr = [x >= 0, a*x == 1]
    prob = cvx.Problem(obj, constr)
    prob.solve()
 
    return np.array(x.value)

# Perform gradient descent to obtain fully-corrective weights.
def fully_corrective_weights(distributions, eps=1e-3, step=.2):
    N = len(distributions)    
    
    weights = geometric_weights(distributions)
    prev_weights = np.zeros(N)
    prev_entropy = 0
    
    print('-- Starting gradient descent --')
    for i in range(100000):
        weights = proj_unit_simplex(weights)
        gradients = np.zeros(N)
        
        # get the d_mix based on the current weights
        d_max = np.zeros(shape=(distributions[0].reshape(-1).shape))
        for w, d in zip(weights, distributions):
            d_max += np.array(w*d).reshape(-1)
        
        log_d_max = np.log(d_max + 1)
        
        for idx in range(N):
            grad_w = -np.sum(distributions[idx].reshape(-1)*log_d_max)
            gradients[idx] = grad_w
        
        entropy = scipy.stats.entropy(d_max)
        norm =  np.linalg.norm(weights - prev_weights)
        
        print('Iteration %d: entropy = %.4f' % (i, entropy))
        print('weights = %s' % str(weights))
        print('norm = %.4f' % norm)

        if abs(entropy - prev_entropy) < eps:
            break
        if norm < 6e-3:
            break
        
        # Step in the direction of the gradient.
        prev_weights = weights
        prev_entropy = entropy
        weights = weights + step*gradients
        
    return weights

# Get (unit-normalized) geometric weights.
def geometric_weights(distributions, gamma=0.90):
    N = len(distributions)
    weights = [gamma**(N-i) for i in range(N)]
    weights = proj_unit_simplex(weights)
    return weights

# Return the proper weighting for the distributions based on command line arguments.
def get_weights(distributions):
    weights = np.ones(len(distributions))/float(len(distributions)) 
    if args.fully_corrective:
        weights = fully_corrective_weights(distributions)
    elif args.geometric:
        weights = geometric_weights(distributions)
    weights = np.absolute(weights) / weights.sum()
    print(weights)
    print(weights.sum())
    
    if not np.isclose(weights.sum(), 1, rtol=1e-8):
        weights /= weights.sum()
        print('re-normalizing: %f' % weights.sum())
    
    return weights

        