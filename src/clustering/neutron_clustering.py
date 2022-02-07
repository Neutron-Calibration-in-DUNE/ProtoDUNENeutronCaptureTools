"""
Collection of clustering functions for neutron calibration sims/data
"""
# imports
import numpy as np
import scipy as sp
import matplotlib.pyplot as plt
import pandas as pd
import uproot
import os
import sys
import math
import csv
import logging
from sklearn import cluster
from sklearn import metrics
import seaborn as sns
#plt.style.use('seaborn-deep')

def load_array(
    input_file,
    array_name,
):
    logging.info(f"Attempting to load array: {array_name} from file: {input_file}.")
    try:
        array = input_file[array_name].arrays(library="np")
        logging.info(f"Successfully loaded array: {array_name} from file: {input_file}.")
    except Exception:
        logging.error(f"Failed to load array: {array_name} from file: {input_file} with exception: {Exception}.")
        raise Exception
    return array

def euclidean_distance(p1, p2):
    if (len(p1) != len(p2)):
        logging.error(f"Tried to compute Euclidean distance between two points with different dimension ({len(p1)},{len(p2)})!")
        raise ValueError(f"Tried to compute Euclidean distance between two points with different dimension ({len(p1)},{len(p2)})!")
    dist = [(a - b)**2 for a, b in zip(p1, p2)]
    dist = math.sqrt(sum(dist))
    return dist

def find_largest_distance(pos):
    dists = []
    for p in pos:
        for q in pos:
            dists.append(
                euclidean_distance(p,q)
            )
    return max(dists)

required_arrays = [
    'event_id',
    'neutron_ids',
    'neutron_capture_x',
    'neutron_capture_y',
    'neutron_capture_z',
    'gamma_ids',
    'gamma_neutron_ids',
    'gamma_energy',
    'edep_energy',
    'edep_parent',
    'edep_neutron_ids',
    'edep_gamma_ids',
    'edep_x',
    'edep_y',
    'edep_z',
    'electron_ids',
    'electron_neutron_ids',
    'electron_gamma_ids',
    'electron_energy',
    'edep_num_electrons',
]

cluster_params = {
    'affinity':     {'damping': 0.5, 'max_iter': 200},
    'mean_shift':   {'bandwidth': None},
    'dbscan':       {'eps': 100.,'min_samples': 6},
    'optics':       {'min_samples': 6},
    'gaussian':     {'n_components': 1, 'covariance_type': 'full', 'tol': 1e-3, 'reg_covar': 1e-6, 'max_iter': 100}
}

class NeutronClusteringMCTruth:
    """
    This class loads simulated neutron events and runs various clustering
    algorithms and analysis.  The arrays in the root file should be structured
    as follows:
        meta:       meta information such as ...
        Geometry:   information about the detector geometry such as volume bounding boxes...
        neutron:    the collection of events from the simulation
        
    The "neutron" array should have the following entries:
        event_id:           the event id for each event (e.g. [0, 7, 18, ...])
        neutron_ids:        track id of each neutron in the event (e.g. [1, 2, 3, ...])
        neutron_capture_x:  the x position of each neutron capture (e.g. [54, 154, ...])
        neutron_capture_y:  the y position ""
        neutron_capture_z:  the z position ""
        gamma_ids:          track id of each gamma that comes from a neutron capture (e.g. [65, 66, ...])
        gamma_neutron_ids:  the track id of the parent of each gamma (e.g. [1, 1, 1, 2, 2, ...])
        gamma_energy (GeV): the energy values of each unique gamma in the event (e.g. [0.004745, ...])
        edep_energy:        the energy values for each deposited energy from a gamma (e.g. [0.00038, ...])
        edep_parent:        the track id of the particle which left the energy deposit ^^^
        edep_neutron_ids:   the track id of the neutron which led to the energy deposit ^^^
        edep_gamma_ids:     the track id of the gamma which left behind each edep in "edep_energy" (e.g. [65, 65, 65, ...])
        edep_x (mm):        the x position of each edep in the event (e.g. [-42, 500.1, ...])
        edep_y (mm):        the y position ""
        edep_z (mm):        the z position ""
        electron_ids:           the track id of each electron tracked in the simulation that comes from a gamma
        electron_neutron_ids:   the corresponding id of the neutron that generated the electron with id ^^^
        electron_gamma_ids:     the corresponding id of the gamma that generated the electron with id ^^^
        electron_energy (GeV):  the energy of each electron tracked in the simulation (e.g. [0.00058097, ...])
        edep_num_electrons:     the number of electrons coming out of the IonAndScint simulation for each edep ^^^
    """
    def __init__(self,
        input_file,
    ):
        # set up logger
        logging.basicConfig(
            level=logging.INFO,
            format="[%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler("neutron_clustering.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )
        logging.info(f"Attempting to load file {input_file}.")
        # load the file
        try:
            self.input_file = uproot.open(input_file)
            logging.info(f"Successfully loaded file {input_file}.")
        except Exception:
            logging.error(f"Failed to load file with exception: {Exception}.")
            raise Exception
        # now load the various arrays
        self.meta       = load_array(self.input_file, 'ana/meta')
        self.geometry   = load_array(self.input_file, 'ana/Geometry')
        self.events     = load_array(self.input_file, 'ana/neutron')

        # construct truth info
        # each index in these arrays correspond to an event
        try:
            self.event_ids          = self.events['event_id']
            self.neutron_ids        = self.events['neutron_ids']
            self.neutron_capture_x  = self.events['neutron_capture_x']
            self.neutron_capture_y  = self.events['neutron_capture_y']
            self.neutron_capture_z  = self.events['neutron_capture_z']
            self.gamma_ids          = self.events['gamma_ids']
            self.gamma_neutron_ids  = self.events['gamma_neutron_ids']
            self.gamma_energy       = self.events['gamma_energy']
            self.edep_energy        = self.events['edep_energy']
            self.edep_parent        = self.events['edep_parent']
            self.edep_neutron_ids   = self.events['edep_neutron_ids']
            self.edep_gamma_ids     = self.events['edep_gamma_ids'] 
            self.x = self.events['edep_x']
            self.y = self.events['edep_y']
            self.z = self.events['edep_z']
            self.electron_ids           = self.events['electron_ids']
            self.electron_neutron_ids   = self.events['electron_neutron_ids']
            self.electron_gamma_ids     = self.events['electron_gamma_ids']
            self.electron_energy        = self.events['electron_energy']
            self.edep_num_electrons     = self.events['edep_num_electrons']
        except:
            logging.error(f"One or more of the required arrays {required_arrays} is not present in {self.events.keys()}.")
            raise ValueError
        self.num_events = len(self.event_ids)
        logging.info(f"Loaded arrays with {self.num_events} entries.")
        self.cluster_predictions = []
        self.cluster_scores = {
            'homogeneity':          [],
            'completeness':         [],
            'v-measure':            [],
            'adjusted_rand_index':  [],
            'adjusted_mutual_info': [],
            'silhouette':           [],
        }
        self.avg_cluster_scores = {
            'homogeneity':          0.,
            'completeness':         0.,
            'v-measure':            0.,
            'adjusted_rand_index':  0.,
            'adjusted_mutual_info': 0.,
            'silhouette':           0.,
        }
        self.cluster_spectrum = []
        # construct positions for clustering
        self.edep_positions = np.array(
            [
                np.array([[
                    self.x[jj][ii],
                    self.y[jj][ii],
                    self.z[jj][ii]]
                    for ii in range(len(self.x[jj]))
                ], dtype=float)
                for jj in range(len(self.x))
            ], 
            dtype=object
        )
        # calculate capture ratio
        self.calculate_capture_ratio()
        # construct TPC boxes
        self.total_tpc_ranges = self.geometry['total_active_tpc_box_ranges']
        self.tpc_x = [self.total_tpc_ranges[0][0], self.total_tpc_ranges[0][1]]
        self.tpc_y = [self.total_tpc_ranges[0][4], self.total_tpc_ranges[0][5]]
        self.tpc_z = [self.total_tpc_ranges[0][2], self.total_tpc_ranges[0][3]]
        self.active_tpc_lines = [
            [[self.tpc_x[0],self.tpc_y[0],self.tpc_z[0]],[self.tpc_x[1],self.tpc_y[0],self.tpc_z[0]]],
            [[self.tpc_x[0],self.tpc_y[0],self.tpc_z[0]],[self.tpc_x[0],self.tpc_y[1],self.tpc_z[0]]],
            [[self.tpc_x[0],self.tpc_y[0],self.tpc_z[0]],[self.tpc_x[0],self.tpc_y[0],self.tpc_z[1]]],
            [[self.tpc_x[0],self.tpc_y[1],self.tpc_z[0]],[self.tpc_x[1],self.tpc_y[1],self.tpc_z[0]]],
            [[self.tpc_x[0],self.tpc_y[1],self.tpc_z[0]],[self.tpc_x[0],self.tpc_y[1],self.tpc_z[1]]],
            [[self.tpc_x[1],self.tpc_y[0],self.tpc_z[0]],[self.tpc_x[1],self.tpc_y[0],self.tpc_z[1]]],
            [[self.tpc_x[1],self.tpc_y[0],self.tpc_z[0]],[self.tpc_x[1],self.tpc_y[1],self.tpc_z[0]]],
            [[self.tpc_x[0],self.tpc_y[1],self.tpc_z[1]],[self.tpc_x[1],self.tpc_y[1],self.tpc_z[1]]],
            [[self.tpc_x[0],self.tpc_y[1],self.tpc_z[1]],[self.tpc_x[0],self.tpc_y[0],self.tpc_z[1]]],
            [[self.tpc_x[1],self.tpc_y[0],self.tpc_z[1]],[self.tpc_x[1],self.tpc_y[1],self.tpc_z[1]]],
            [[self.tpc_x[1],self.tpc_y[0],self.tpc_z[1]],[self.tpc_x[0],self.tpc_y[0],self.tpc_z[1]]],
            [[self.tpc_x[1],self.tpc_y[1],self.tpc_z[0]],[self.tpc_x[1],self.tpc_y[1],self.tpc_z[1]]],
        ]
        # cryostat boundary
        self.total_cryo_ranges = self.geometry['cryostat_box_ranges']
        self.cryo_x = [self.total_cryo_ranges[0][0], self.total_cryo_ranges[0][1]]
        self.cryo_y = [self.total_cryo_ranges[0][4], self.total_cryo_ranges[0][5]]
        self.cryo_z = [self.total_cryo_ranges[0][2], self.total_cryo_ranges[0][3]]
        self.cryostat_lines = [
            [[self.cryo_x[0],self.cryo_y[0],self.cryo_z[0]],[self.cryo_x[1],self.cryo_y[0],self.cryo_z[0]]],
            [[self.cryo_x[0],self.cryo_y[0],self.cryo_z[0]],[self.cryo_x[0],self.cryo_y[1],self.cryo_z[0]]],
            [[self.cryo_x[0],self.cryo_y[0],self.cryo_z[0]],[self.cryo_x[0],self.cryo_y[0],self.cryo_z[1]]],
            [[self.cryo_x[0],self.cryo_y[1],self.cryo_z[0]],[self.cryo_x[1],self.cryo_y[1],self.cryo_z[0]]],
            [[self.cryo_x[0],self.cryo_y[1],self.cryo_z[0]],[self.cryo_x[0],self.cryo_y[1],self.cryo_z[1]]],
            [[self.cryo_x[1],self.cryo_y[0],self.cryo_z[0]],[self.cryo_x[1],self.cryo_y[0],self.cryo_z[1]]],
            [[self.cryo_x[1],self.cryo_y[0],self.cryo_z[0]],[self.cryo_x[1],self.cryo_y[1],self.cryo_z[0]]],
            [[self.cryo_x[0],self.cryo_y[1],self.cryo_z[1]],[self.cryo_x[1],self.cryo_y[1],self.cryo_z[1]]],
            [[self.cryo_x[0],self.cryo_y[1],self.cryo_z[1]],[self.cryo_x[0],self.cryo_y[0],self.cryo_z[1]]],
            [[self.cryo_x[1],self.cryo_y[0],self.cryo_z[1]],[self.cryo_x[1],self.cryo_y[1],self.cryo_z[1]]],
            [[self.cryo_x[1],self.cryo_y[0],self.cryo_z[1]],[self.cryo_x[0],self.cryo_y[0],self.cryo_z[1]]],
            [[self.cryo_x[1],self.cryo_y[1],self.cryo_z[0]],[self.cryo_x[1],self.cryo_y[1],self.cryo_z[1]]],
        ]

    def plot_event(self,
        index,
        label:  str='neutron',  # plot by neutron, gamma, electron
        title:  str='',
        legend_cutoff:  int=10, # only show the first N labels in the legend (gets crammed easily)
        show_active_tpc: bool=True,
        show_cryostat:   bool=True,
        save:   str='',
        show:   bool=True,
    ):
        if index >= self.num_events:
            logging.error(f"Tried accessing element {index} of array with size {self.num_events}!")
            raise IndexError(f"Tried accessing element {index} of array with size {self.num_events}!")
        if label not in ['neutron', 'gamma']:
            logging.warning(f"Requested labeling by '{label}' not allowed, using 'neutron'.")
            label = 'neutron'
        fig = plt.figure(figsize=(8,6))
        axs = fig.add_subplot(projection='3d')
        x, y, z, ids, energy = [], [], [], [], []
        indices = []
        if label == 'neutron':
            labels = np.unique(self.edep_neutron_ids[index])
            for ii, value in enumerate(labels):
                indices.append(np.where(self.edep_neutron_ids[index] == value))
        else:
            labels = np.unique(self.edep_gamma_ids[index])
            for ii, value in enumerate(labels):
                indices.append(np.where(self.edep_gamma_ids[index] == value))
        for ii, value in enumerate(labels):
            x.append([self.x[index][indices[ii]]])
            y.append([self.z[index][indices[ii]]])
            z.append([self.y[index][indices[ii]]])
            energy.append([1000*self.edep_energy[index][indices[ii]]])
            ids.append(f'{label} {ii}: (id: {value}, energy: {round(sum(self.edep_energy[index][indices[ii]]),4)} MeV)')
        for jj in range(len(x)):
            if jj < legend_cutoff:
                axs.scatter3D(x[jj], y[jj], z[jj], label=ids[jj], s=energy[jj])
            else:
                axs.scatter3D(x[jj], y[jj], z[jj], s=energy[jj])
        axs.set_xlabel("x (mm)")
        axs.set_ylabel("z (mm)")
        axs.set_zlabel("y (mm)")
        axs.set_title(title)
        # draw the active tpc volume box
        if show_active_tpc:
            for i in range(len(self.active_tpc_lines)):
                x = np.array([self.active_tpc_lines[i][0][0],self.active_tpc_lines[i][1][0]])
                y = np.array([self.active_tpc_lines[i][0][1],self.active_tpc_lines[i][1][1]])
                z = np.array([self.active_tpc_lines[i][0][2],self.active_tpc_lines[i][1][2]])
                if i == 0:
                    axs.plot(x,y,z,linestyle='--',color='b',label='Active TPC volume')
                else:
                    axs.plot(x,y,z,linestyle='--',color='b')
        if show_cryostat:
            for i in range(len(self.cryostat_lines)):
                x = np.array([self.cryostat_lines[i][0][0],self.cryostat_lines[i][1][0]])
                y = np.array([self.cryostat_lines[i][0][1],self.cryostat_lines[i][1][1]])
                z = np.array([self.cryostat_lines[i][0][2],self.cryostat_lines[i][1][2]])
                if i == 0:
                    axs.plot(x,y,z,linestyle=':',color='g',label='Cryostat volume')
                else:
                    axs.plot(x,y,z,linestyle=':',color='g')
        plt.legend()
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+'.png')
        if show:
            plt.show()

    def cluster(self,
        level:  str='neutron',
        alg:    str='dbscan',
        params: dict={'eps': 100.,'min_samples': 6},
    ):
        """
        Function for running clustering algorithms on events.
        The level can be ['neutron','gamma']
        """
        if level not in ['neutron', 'gamma']:
            logging.warning(f"Requested cluster level by '{level}' not allowed, using 'neutron'.")
            level = 'neutron'
        if alg not in cluster_params.keys():
            logging.warning(f"Requested algorithm '{alg}' not allowed, using 'dbscan'.")
            alg = 'dbscan'
            params = cluster_params['dbscan']
        # check params
        for item in params:
            if item not in cluster_params[alg]:
                logging.error(f"Unrecognized parameter {item} for algorithm {alg}! Available parameters are {cluster_params[alg]}.")
                raise ValueError(f"Unrecognized parameter {item} for algorithm {alg}! Available parameters are {cluster_params[alg]}.")
        # run the clustering algorithm
        logging.info(f"Attempting to run clustering algorithm {alg} with parameters {params}.")
        if alg == 'affinity':
            clusterer = cluster.AffinityPropagation(**params)
        elif alg == 'mean_shift':
            clusterer = cluster.MeanShift(**params)
        elif alg == 'optics':
            clusterer = cluster.OPTICS(**params)
        elif alg == 'gaussian':
            clusterer = cluster.GaussianMixture(**params)
        else:
            clusterer = cluster.DBSCAN(**params)
        self.cluster_predictions = []
        for pos in self.edep_positions:
            clusterer.fit(pos)
            self.cluster_predictions.append(clusterer.labels_)

    def calc_scores(self,
        level:  str='neutron',
    ):
        if level not in ['neutron', 'gamma']:
            logging.warning(f"Requested cluster level by '{level}' not allowed, using 'neutron'.")
            level = 'neutron'
        if self.cluster_predictions == []:
            logging.error("No predictions have been made, need to run clustering algorithm first!")
            raise ValueError("No predictions have been made, need to run clustering algorithm first!")
        if len(self.cluster_predictions) != self.num_events:
            logging.error(f"Only {len(self.cluster_predictions)} predictions but {self.num_events} events!")
            raise ValueError(f"Only {len(self.cluster_predictions)} predictions but {self.num_events} events!")
        # clear the scores
        for item in self.cluster_scores.keys():
            self.cluster_scores[item] = []
        if level == 'neutron':
            labels = self.edep_neutron_ids
        else:
            labels = self.edep_gamma_ids
        logging.info(f"Attempting to calculate scores on cluster predictions for level: {level}.")
        for ii, pred in enumerate(self.cluster_predictions):
            self.cluster_scores['homogeneity'].append(metrics.homogeneity_score(labels[ii], pred))
            self.cluster_scores['completeness'].append(metrics.completeness_score(labels[ii], pred))
            self.cluster_scores['v-measure'].append(metrics.v_measure_score(labels[ii], pred))
            self.cluster_scores['adjusted_rand_index'].append(metrics.adjusted_rand_score(labels[ii], pred))
            self.cluster_scores['adjusted_mutual_info'].append(metrics.adjusted_mutual_info_score(labels[ii], pred))
            self.cluster_scores['silhouette'].append(metrics.silhouette_score(self.edep_positions[ii], pred))
        for item in self.cluster_scores.keys():
            self.avg_cluster_scores[item] = sum(self.cluster_scores[item]) / len(labels)
        logging.info(f"Calculated average scores {self.avg_cluster_scores} for level: {level}.")
        return self.avg_cluster_scores

    def plot_prediction_spectrum(self,
        num_bins:   int=100,
        edep_type:  str='true',
        energy_cut: float=10.,   # MeV
        title:  str='Example Prediction Spectrum',
        save:   str='',
        show:   bool=True,
    ):
        if edep_type not in ['true','ion_scint','compare']:
            logging.warning(f"Requested edep type '{edep_type}' not allowed, using 'true'.")
            edep_type = 'true'
        if self.cluster_predictions == []:
            logging.error("No predictions have been made, need to run clustering algorithm first!")
            raise ValueError("No predictions have been made, need to run clustering algorithm first!")
        if len(self.cluster_predictions) != self.num_events:
            logging.error(f"Only {len(self.cluster_predictions)} predictions but {self.num_events} events!")
            raise ValueError(f"Only {len(self.cluster_predictions)} predictions but {self.num_events} events!")
        # find cluster energies
        if edep_type == 'compare':
            self.cluster_spectrum = [[],[]]
        else:
            self.cluster_spectrum = [[]]
        for ii, pred in enumerate(self.cluster_predictions):
            clusters = np.unique(pred)
            for cluster in clusters:
                indices = np.where(pred==cluster)
                if edep_type == 'true':
                    true_energies = sum(self.edep_energy[ii][indices])
                    if true_energies < energy_cut:
                        self.cluster_spectrum[0].append(true_energies)
                elif edep_type == 'ion_scint':
                    ion_scint_energies = sum(self.edep_num_electrons[ii][indices]*1.5763e-5)  # eV of Ar ionization (MeV)
                    if ion_scint_energies < energy_cut:
                        self.cluster_spectrum[0].append(ion_scint_energies)
                else:
                    true_energies = sum(self.edep_energy[ii][indices])
                    ion_scint_energies = sum(self.edep_num_electrons[ii][indices]*1.5763e-5)
                    if (true_energies < energy_cut and ion_scint_energies < energy_cut):
                        self.cluster_spectrum[0].append(true_energies)
                        self.cluster_spectrum[1].append(ion_scint_energies)
        fig, axs = plt.subplots()
        if len(self.cluster_spectrum) == 1:
            axs.hist(self.cluster_spectrum[0], bins=num_bins, label=edep_type)
        else:
            axs.hist(self.cluster_spectrum[0], bins=num_bins, label='true', histtype='step', density=True, stacked=True)
            axs.hist(self.cluster_spectrum[1], bins=num_bins, label='ion_scint', histtype='step', density=True, stacked=True)
        axs.set_xlabel('Cluster Energy (MeV)')
        axs.set_xticks(axs.get_xticks() + [6.098])
        axs.set_xlim(0,energy_cut)
        axs.set_title(title)
        plt.legend()
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+'.png')
        if show:
            plt.show()

    def calculate_capture_ratio(self):
        # keep track of the ratio of complete 6.098
        # captures vs total.
        logging.info(f"Attempting to calculate capture ratio.")
        self.num_complete_captures = []
        self.num_captures = []
        # loop through all edeps
        for ii, truth in enumerate(self.edep_neutron_ids):
            complete = 0
            total = 0
            clusters = np.unique(truth)
            for cluster in clusters:
                indices = np.where(truth==cluster)
                true_energies = sum(self.edep_energy[ii][indices])
                total += 1
                if round(true_energies,2) == 6.1:
                    complete += 1
            self.num_captures.append(total)
            self.num_complete_captures.append(complete)
        self.capture_ratio = round((sum(self.num_complete_captures)/sum(self.num_captures))*100)

    def plot_true_spectrum(self,
        num_bins:   int=100,
        energy_cut: float=10.,   # MeV
        title:  str='Example MC Spectrum',
        save:   str='',
        show:   bool=True,
    ):
        cluster_spectrum = []
        # loop through all edeps
        for ii, truth in enumerate(self.edep_neutron_ids):
            complete = 0
            total = 0
            clusters = np.unique(truth)
            for cluster in clusters:
                indices = np.where(truth==cluster)
                true_energies = sum(self.edep_energy[ii][indices])
                if (true_energies < energy_cut):
                    self.cluster_spectrum.append(true_energies)
        fig, axs = plt.subplots()
        axs.hist(self.cluster_spectrum, bins=num_bins, label='mc spectrum')
        axs.set_xlabel(rf'Capture Energy (MeV) - Complete Capture Ratio ({sum(self.num_complete_captures)}/{sum(self.num_captures)})$\approx${self.capture_ratio}%')
        axs.set_xticks(axs.get_xticks() + [6.098])
        axs.set_xlim(0,energy_cut)
        axs.set_title(title)
        plt.legend()
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+'.png')
        if show:
            plt.show()
    
    def plot_capture_locations(self,
        event:  int,
        plot_type:   str='3d',
        show_active_tpc:    bool=True,
        show_cryostat:      bool=True,
        title:  str='Example MC Capture Locations',
        save:   str='',
        show:   bool=True,
    ):
        if event >= self.num_events:
            logging.error(f"Tried accessing element {event} of array with size {self.num_events}!")
            raise IndexError(f"Tried accessing element {event} of array with size {self.num_events}!")
        if plot_type not in ['3d', 'xy', 'xz', 'yz']:
            logging.warning(f"Requested plot type '{plot_type}' not allowed, using '3d'.")
            plot_type = '3d'
        if plot_type == '3d':
            fig = plt.figure(figsize=(8,6))
            axs = fig.add_subplot(projection='3d')
            axs.scatter(
                self.neutron_capture_x[event],
                self.neutron_capture_z[event],
                self.neutron_capture_y[event]
            )
            axs.set_xlabel("x (mm)")
            axs.set_ylabel("z (mm)")
            axs.set_zlabel("y (mm)")
            # draw the active tpc volume box
        else:
            fig, axs = plt.subplots(figsize=(8,6))
            if plot_type == 'xz':
                axs.scatter(self.neutron_capture_x[event], self.neutron_capture_z[event])
                axs.set_xlabel("x (mm)")
                axs.set_ylabel("z (mm)")
            elif plot_type == 'yz':
                axs.scatter(self.neutron_capture_y[event], self.neutron_capture_z[event])
                axs.set_xlabel("y (mm)")
                axs.set_ylabel("z (mm)")
            else:
                axs.scatter(self.neutron_capture_x[event], self.neutron_capture_y[event])
                axs.set_xlabel("x (mm)")
                axs.set_ylabel("y (mm)")
        if show_active_tpc:
            for i in range(len(self.active_tpc_lines)):
                x = np.array([self.active_tpc_lines[i][0][0],self.active_tpc_lines[i][1][0]])
                y = np.array([self.active_tpc_lines[i][0][1],self.active_tpc_lines[i][1][1]])
                z = np.array([self.active_tpc_lines[i][0][2],self.active_tpc_lines[i][1][2]])
                if plot_type == '3d':
                    if i == 0:
                        axs.plot(x,y,z,linestyle='--',color='b',label='Active TPC volume')
                    else:
                        axs.plot(x,y,z,linestyle='--',color='b')
                elif plot_type == 'xz':
                    if i == 0:
                        axs.plot(x,y,linestyle='--',color='b',label='Active TPC volume')
                    else:
                        axs.plot(x,y,linestyle='--',color='b')
                elif plot_type == 'yz':
                    if i == 0:
                        axs.plot(z,y,linestyle='--',color='b',label='Active TPC volume')
                    else:
                        axs.plot(z,y,linestyle='--',color='b')
                else:
                    if i == 0:
                        axs.plot(x,z,linestyle='--',color='b',label='Active TPC volume')
                    else:
                        axs.plot(x,z,linestyle='--',color='b')
        if show_cryostat:
            for i in range(len(self.cryostat_lines)):
                x = np.array([self.cryostat_lines[i][0][0],self.cryostat_lines[i][1][0]])
                y = np.array([self.cryostat_lines[i][0][1],self.cryostat_lines[i][1][1]])
                z = np.array([self.cryostat_lines[i][0][2],self.cryostat_lines[i][1][2]])
                if plot_type == '3d':
                    if i == 0:
                        axs.plot(x,y,z,linestyle=':',color='g',label='Cryostat volume')
                    else:
                        axs.plot(x,y,z,linestyle=':',color='g')
                elif plot_type == 'xz':
                    if i == 0:
                        axs.plot(x,y,linestyle=':',color='g',label='Cryostat volume')
                    else:
                        axs.plot(x,y,linestyle=':',color='g')
                elif plot_type == 'yz':
                    if i == 0:
                        axs.plot(z,y,linestyle=':',color='g',label='Cryostat volume')
                    else:
                        axs.plot(z,y,linestyle=':',color='g')
                else:
                    if i == 0:
                        axs.plot(x,z,linestyle=':',color='g',label='Cryostat volume')
                    else:
                        axs.plot(x,z,linestyle=':',color='g')
        axs.set_title(title)
        plt.legend()
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+'.png')
        if show:
            plt.show()
    
    def plot_capture_density(self,
        plot_type:   str='xy',
        density_type:       str='kde',
        show_active_tpc:    bool=True,
        show_cryostat:      bool=True,
        title:  str='Example MC Capture Locations',
        save:   str='',
        show:   bool=True,
    ):
        if plot_type not in ['xy', 'xz', 'yz']:
            logging.warning(f"Requested plot type '{plot_type}' not allowed, using 'xy'.")
            plot_type = 'xy'
        if density_type not in ['scatter', 'kde', 'hist', 'hex', 'reg', 'resid']:
            logging.warning(f"Requested density type {density_type} not allowed, using 'kde'.")
            density_type = 'kde'
        if plot_type == 'xz':
            x = np.concatenate([xi for xi in self.neutron_capture_x]).flatten()
            y = np.concatenate([zi for zi in self.neutron_capture_z]).flatten()
        elif plot_type == 'yz':
            x = np.concatenate([yi for yi in self.neutron_capture_y]).flatten()
            y = np.concatenate([zi for zi in self.neutron_capture_z]).flatten()
        else:
            x = np.concatenate([xi for xi in self.neutron_capture_x]).flatten()
            y = np.concatenate([yi for yi in self.neutron_capture_y]).flatten()
        sns.jointplot(x=x, y=y, kind=density_type, palette='crest')
        if plot_type == 'xz':
            plt.xlabel("x (mm)")
            plt.ylabel("z (mm)")
        elif plot_type == 'yz':
            plt.xlabel("y (mm)")
            plt.ylabel("z (mm)")
        else:
            plt.xlabel("x (mm)")
            plt.ylabel("y (mm)")
        plt.title(title)
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+'.png')
        if show:
            plt.show()

    def scan_eps_values(self,
        eps_range:  list=[1.,100.],
        eps_step:   float=1.,
        save_scores:    str='scan_scores'
    ):
        num_steps = int((eps_range[1] - eps_range[0])/eps_step)
        eps_values = [eps_range[0] + ii*eps_step for ii in range(num_steps)]
        scores = [['eps','homogeneity','completeness','v-measure','adjusted_rand_index','adjusted_mutual_info','silhouette']]
        logging.info(f"Attempting to run scanning search with {num_steps} eps values from {eps_values[0]} to {eps_values[-1]}.")
        for eps in eps_values:
            logging.info(f"Running clustering for eps = {eps}.")
            neutron_clustering.cluster(
                alg = 'dbscan',
                params = {'eps': eps, 'min_samples': 6}
            )
            logging.info(f"Computing scores for eps = {eps}.")
            avg_scores = neutron_clustering.calc_scores()
            score_list = [eps]
            for item in avg_scores.keys():
                score_list.append(avg_scores[item])
            scores.append(score_list)
        with open(save_scores+".csv","w") as file:
            writer = csv.writer(file, delimiter=",")
            writer.writerows(scores)
    
    def plot_eps_scores(self,
        input_file,
        save:   str='',
        show:   bool=True
    ):
        scores = pd.read_csv(input_file,delimiter=",")
        if 'eps' not in scores.keys():
            logging.error(f"Column for 'eps' values not present in {input_file}: {scores.keys()}")
            raise ValueError(f"Column for 'eps' values not present in {input_file}: {scores.keys()}")
        eps_values = scores['eps']
        fig, axs = plt.subplots(figsize=(8,6))
        for item in scores.keys():
            if item != 'eps':
                axs.plot(
                    eps_values, 
                    scores[item],  
                    linestyle='--'
                )
                max_index = np.argmax(scores[item])
                axs.scatter(
                    eps_values[max_index],
                    scores[item][max_index],
                    label=f'{item} - max ({eps_values[max_index]},{round(scores[item][max_index],3)})',
                    marker='x'
                )
        axs.set_xlabel('eps (mm)')
        axs.set_ylabel('metric')
        axs.set_title('Clustering metric vs. eps (mm)')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+".png")
        if show:
            plt.show()
    
    def fit_depth_exponential(self,
        num_bins:   int=100,
        save:   str='',
        show:   bool=True
    ):
        y_pos = np.concatenate([yi for yi in self.y]).flatten()
        # normalize positions
        y_max = np.max(y_pos)
        depth = np.abs(y_max - y_pos)
        # fit histogram
        y_hist, y_edges = np.histogram(depth, bins=num_bins)
        hist_sum = sum(y_hist)
        y_hist = y_hist.astype(float) / hist_sum
        # determine cumulative hist
        cum_hist = [y_hist[0]]
        for ii in range(1,len(y_hist)):
            cum_hist.append(y_hist[ii]+cum_hist[-1])
        # arrange mid points for fit
        mid_points = np.array([y_edges[ii] + (y_edges[ii+1]-y_edges[ii])/2. for ii in range(len(y_hist))])
        # fit to logarithm
        exp_fit = sp.optimize.curve_fit(
            lambda t,a,b: a*np.exp(-b*t),   # decaying exponential
            mid_points, 
            y_hist
        )
        exp_function = exp_fit[0][0] * np.exp(-exp_fit[0][1] * mid_points)
        # plot the results
        fig, axs = plt.subplots(figsize=(8,6))
        axs.scatter(mid_points, y_hist, label='hist')
        axs.plot(
            mid_points, 
            exp_function, 
            label=rf'fit ($\sim\exp[-{round(exp_fit[0][1],3)}\, \Delta y]$)'
        )
        axs.set_xlabel(r'depth - $\Delta y$ - (mm)')
        axs.set_ylabel('density (height/sum)')
        plt.legend(loc='center right')
        axs2 = axs.twinx()
        axs2.plot(
            mid_points,
            cum_hist,
        )
        axs2.set_ylabel('cummulative %')
        axs.set_title('Capture density vs. depth (mm)')
        plt.grid(True)
        
        plt.tight_layout()
        if save != '':
            plt.savefig('plots/'+save+'.png')
        if show:
            plt.show()
    


if __name__ == "__main__":

    neutron_clustering = NeutronClusteringMCTruth(
        "../neutron_data/simple_sims/NeutronDataset_50_1450.root"
    )
    neutron_clustering.fit_depth_exponential(
        num_bins=100,
        save='depth_exp'
    )

    # plot 3d and xz views of capture locations
    # neutron_clustering.plot_capture_locations(
    #     event = 0,
    #     plot_type = '3d',
    #     title = 'Example Capture Locations (FDSP 1x2x6)',
    #     save = 'fdsp_1x2x6_3d',
    #     show = False
    # )
    # neutron_clustering.plot_capture_locations(
    #     event = 0,
    #     plot_type = 'xz',
    #     title = 'Example Capture Locations (FDSP 1x2x6)',
    #     save = 'fdsp_1x2x6_xz',
    #     show = False
    # )
    # neutron_clustering.plot_capture_locations(
    #     event = 0,
    #     plot_type = 'xy',
    #     title = 'Example Capture Locations (FDSP 1x2x6)',
    #     save = 'fdsp_1x2x6_xy',
    #     show = False
    # )
    # neutron_clustering.plot_capture_density(
    #     plot_type = 'xy',
    #     density_type ='hex',
    #     save = 'fdsp_1x2x6_xy_hex',
    #     show = False
    # )
    # neutron_clustering.plot_eps_scores(
    #     input_file = "scan_scores.csv",
    #     save = 'scan_scores'
    # )

    # neutron_clustering.scan_eps_values(
    #     eps_range = [1., 100.],
    #     eps_step = 1.
    # )

    # run the clustering algorithm
    # neutron_clustering.cluster(
    #     alg = 'dbscan',
    #     params = {'eps': 30, 'min_samples': 6}
    # )
    # avg_scores = neutron_clustering.calc_scores()

    # print(f"clustering scores: ")
    # for item in avg_scores.keys():
        
    #     print(f"    - {item}: {avg_scores[item]}.")
    # neutron_clustering.plot_true_spectrum(
    #     save = 'true_spectrum'
    # )
    # neutron_clustering.plot_prediction_spectrum(
    #     edep_type = 'compare',
    #     save = 'clustering_spectrum'
    # )
    # neutron_clustering.plot_event(
    #     index = 10, 
    #     label = 'neutron',
    #     title = 'Example Capture',
    #     save = 'example_event' 
    # )