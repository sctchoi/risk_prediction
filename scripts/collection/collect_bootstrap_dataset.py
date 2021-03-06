"""

# outline
1. while loop
2. collect dataset with julia
    - initial collection without network
    - subsequently with filepath to network
    - each with output filepath for dataset
3. train a network to convergence on that dataset
    - load flags from run_compression.py
    - then just do a normal tf setup where you frun fit on each dataset

# flags
- python flags
    + julia_weights_filepath
        * where to save the julia weights
    + dataset_filepath
        * becomes output_filepath (where to save the datasets)
- julia flags
    + evaluator_type
        * type of eval (base, bootstrap)
    + output_filepath
        * where to save 
    + network_filepath
        * filepath to bootstrap network

# cmd
## debug
python collect_bootstrap_dataset.py \
--dataset_filepath ../../data/datasets/bootstrap/ \
--num_scenarios 10000 \
--num_monte_carlo_runs 1 \
--bootstrap_iterations 50 \
--julia_weights_filepath ../../data/networks/bootstrap/ \
--debug_lo_delta_s 10. \
--debug_hi_delta_s 10. \
--debug_lo_v_rear 0. \
--debug_hi_v_rear 0. \
--debug_lo_v_fore 0. \
--debug_hi_v_fore 0. \
--debug_rear_sigma 0. \
--debug_fore_sigma 0. \
--debug_v_eps 2. \
--prime_time .1 \
--sampling_time .1 \
--input_dim 40 \
--monitor_scenario_record_freq 10000 \
--num_epochs 50 \
--decay_lr_ratio .95 \
--run_filepath run_collect_debug_dataset.jl

"""

import numpy as np
import os
import subprocess
import sys
import tensorflow as tf

path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.append(os.path.abspath(path))

import compression.compression_flags as compression_flags
import compression.compression_metrics as compression_metrics
import compression.run_compression as run_compression
import dataset
import dataset_loaders
import neural_networks.feed_forward_neural_network as ffnn
import neural_networks.utils

def generate_dataset(flags, dataset_filepath, network_filepath):
    # if this is the first dataset, then collect a basic dataset
    evaluator_type = 'base' if network_filepath == 'none' else 'bootstrap'
    proc_string = '-p {}'.format(flags.num_proc) if flags.num_proc > 1 else ''
    # format the subprocess command
    cmd = 'julia {} {} --evaluator_type {} --output_filepath {} --network_filepath {} --initial_seed {} '.format(
        proc_string, flags.run_filepath, evaluator_type, dataset_filepath,
        network_filepath, flags.initial_seed)
    # append all of the command line arguments not used in flags, because they 
    # must then have been intended for the dataset collection process
    for idx in range(1, len(sys.argv) - 1, 2):
        arg, val = sys.argv[idx], sys.argv[idx + 1]

        # pass all the arguments to julia, the invalid ones will be ignored
        if len(arg) > 2:
            parsed_arg = arg[2:]
            cmd += arg + ' ' + val + ' '

    print(cmd)

    # call the julia process to collect the dataset
    subprocess.call(cmd, shell=True, stderr=subprocess.STDOUT)

def main(argv=None):
    # use the flags from regular compression
    FLAGS = compression_flags.FLAGS

    # custom parse of flags for list input
    compression_flags.custom_parse_flags(FLAGS)

    # set random seeds
    np.random.seed(FLAGS.random_seed)
    tf.set_random_seed(FLAGS.random_seed)

    # where to save the intermediate datasets
    basedir = os.path.split(FLAGS.dataset_filepath)[0]
    if not os.path.exists(basedir):
        os.mkdir(basedir)
    dataset_filepath_template = os.path.join(basedir, 'iter_{}.h5')

    # where to save the networks
    basedir = os.path.split(FLAGS.julia_weights_filepath)[0]
    if not os.path.exists(basedir):
        os.mkdir(basedir)
    network_filepath_template = os.path.join(basedir, 'iter_{}.weights')

    # need some way to convey to the dataset collector the seed at which it 
    # should begin collection. Accomplish this by tracking the value in flags
    FLAGS.initial_seed = 1

    # create the model then repeatedly collect and fit datasets
    with tf.Session() as session:

        # build the network to use throughout training
        network = ffnn.FeedForwardNeuralNetwork(session, FLAGS)

        # none signifies non bootstrap dataset 
        network_filepath = FLAGS.initial_network_filepath

        for bootstrap_iter in range(FLAGS.bootstrap_iterations):
            
            # generate a dataset
            dataset_filepath = dataset_filepath_template.format(bootstrap_iter)
            FLAGS.dataset_filepath = dataset_filepath
            generate_dataset(FLAGS, dataset_filepath, network_filepath)

            # load in the dataset
            data = dataset_loaders.risk_dataset_loader(dataset_filepath,
                normalize=True, shuffle=True, train_split=.9, 
                debug_size=FLAGS.debug_size, timesteps=FLAGS.timesteps)
            d = dataset.Dataset(data, FLAGS)

            # fit the network to the dataset
            network.fit(d)

            # evaluate the fit
            compression_metrics.evaluate_fit(network, data, FLAGS)

            # save weights to a julia-compatible weight file for next iteration
            network_filepath = network_filepath_template.format(bootstrap_iter)
            neural_networks.utils.save_trainable_variables(
                network_filepath, session, data)

            # increment the initial seed by the number of scenarios simulated 
            # during each collection iteration
            FLAGS.initial_seed += FLAGS.num_scenarios

if __name__ == '__main__':
    tf.app.run()

