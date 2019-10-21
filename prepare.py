"""
Data preparation script which reads HDF5 files and produces TFRecords.
"""

# System
import os
import argparse
import logging
import multiprocessing as mp
from functools import partial

# Externals
import h5py
import numpy as np
import tensorflow as tf

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-dir', default='/project/projectdirs/m3363/www/cosmoUniverse_2019_05_4parE')
    parser.add_argument('-o', '--output-dir', default='/global/cscratch1/sd/sfarrell/cosmoflow-benchmark/data/cosmoUniverse_2019_05_4parE_tf')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--sample-size', type=int, default=128)
    parser.add_argument('--max-files', type=int)
    parser.add_argument('--n-workers', type=int, default=1)
    parser.add_argument('--task', type=int, default=0)
    parser.add_argument('--n-tasks', type=int, default=1)
    return parser.parse_args()

def find_files(input_dir, max_files=None):
    files = []
    for subdir, _, subfiles in os.walk(input_dir):
        for f in subfiles:
            if f.endswith('hdf5'):
                files.append(os.path.join(subdir, f))
    files = sorted(files)
    if max_files is not None:
        files = files[:max_files]
    return files

def read_hdf5(file_path):
    with h5py.File(file_path, mode='r') as f:
        x = f['full'][:]
        y = f['unitPar'][:]
    return x, y

def split_universe(x, size):
    """Generator function for iterating over the sub-universes"""
    n = x.shape[0] // size
    # Loop over each sub-sample index
    for i in range(n):
        istart, iend = i * size, (i + 1) * size
        for j in range(n):
            jstart, jend = j * size, (j + 1) * size
            for k in range(n):
                kstart, kend = k * size, (k + 1) * size
                yield x[istart : iend, jstart : jend, kstart : kend]

def write_record(output_file, example):
    with tf.io.TFRecordWriter(output_file) as writer:
        writer.write(example.SerializeToString())

def process_file(input_file, output_dir, sample_size):
    logging.info('Reading %s', input_file)

    # Load the data
    x, y = read_hdf5(input_file)

    # Loop over sub-volumes
    for i, xi in enumerate(split_universe(x, sample_size)):

        # Convert to TF example
        feature_dict = dict(
            x=tf.train.Feature(float_list=tf.train.FloatList(value=xi.flatten())),
            y=tf.train.Feature(float_list=tf.train.FloatList(value=y)))
        tf_example = tf.train.Example(features=tf.train.Features(feature=feature_dict))

        # Determine output file name
        output_file = os.path.join(
            output_dir,
            os.path.basename(input_file).replace('.hdf5', '_%03i.tfrecord' % i)
        )

        # Write the output file
        logging.info('Writing %s', output_file)
        write_record(output_file, tf_example)

def main():
    """Main function"""

    # Parse the command line
    args = parse_args()

    # Setup logging
    log_format = '%(asctime)s %(levelname)s %(message)s'
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format=log_format)
    logging.info('Initializing')

    # Prepare output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Loop over input files
    input_files = find_files(args.input_dir, max_files=args.max_files)
    # Split the file list by number of tasks and select my subset
    input_files = np.array_split(input_files, args.n_tasks)[args.task]

    # Process input files with a worker pool
    with mp.Pool(processes=args.n_workers) as pool:
        process_func = partial(process_file, output_dir=args.output_dir,
                               sample_size=args.sample_size)
        pool.map(process_func, input_files)

    logging.info('All done!')

if __name__ == '__main__':
    main()
