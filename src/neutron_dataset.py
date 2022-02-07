"""
Collection of classes for generating cosmic ray datasets
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
from sklearn import cluster
from sklearn import metrics
import seaborn as sns
import torch
import torch.nn as nn
from torch.utils.data import Dataset
from unet_logger import UNetLogger
import MinkowskiEngine as ME


required_neutron_arrays = [
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

required_muon_arrays = [
    'primary_muons',
    'muon_ids',
    'muon_edep_ids',
    'muon_edep_energy',
    'muon_edep_num_electrons',
    'muon_edep_x',
    'muon_edep_y',
    'muon_edep_z',
]

required_voxel_arrays = [
    "x_min", 
    "x_max", 
    "y_min", 
    "y_max", 
    "z_min", 
    "z_max", 
    "voxel_size", 
    "num_voxels_x",
    "num_voxels_y",
    "num_voxels_z",
    "x_id", 
    "y_id", 
    "z_id", 
    "values",
    "labels",
]

class NeutronCosmicDataset:
    """
    This class loads simulated neutron events and runs various clustering
    algorithms and analysis.  The arrays in the root file should be structured
    as follows:
        meta:       meta information such as ...
        Geometry:   information about the detector geometry such as volume bounding boxes...
        neutron:    the collection of neutron event information from the simulation
        muon:       the collection of muon event information
        voxels:     the collection of voxelized truth/reco information
        
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
    
    The "muon" array should have the following entries:
        primary_muons:      the number of muons in the event
        muon_ids:           the track ids of the muons
        muon_edep_ids:      the track id of the corresponding muon that left the energy deposit
        muon_edep_energy:   the energy values of each unique deposit
        muon_edep_num_electrons:    the number of electrons generated from each energy deposit
        muon_edep_x:        the x position of each edep from muons
        muon_edep_y:        the y ""
        muon_edep_z:        the z ""
    """
    def __init__(self,
        input_file,
        load_neutrons:  bool=True,
        load_muons:     bool=True,
        load_ar39:      bool=True,
        load_voxels:    bool=True,
    ):
        self.load_neutrons = load_neutrons
        self.load_muons    = load_muons
        self.load_ar39     = load_ar39
        self.load_voxels   = load_voxels
        self.logger = UNetLogger('neutron_dataset', file_mode='w')
        self.logger.info(f"Attempting to load file {input_file}.")
        # load the file
        try:
            self.input_file = uproot.open(input_file)
            self.logger.info(f"Successfully loaded file {input_file}.")
        except Exception:
            self.logger.error(f"Failed to load file with exception: {Exception}.")
            raise Exception
        # now load the various arrays
        self.meta       = self.load_array(self.input_file, 'ana/meta')
        self.geometry   = self.load_array(self.input_file, 'ana/Geometry')
        if load_neutrons:
            self.neutron    = self.load_array(self.input_file, 'ana/neutron')
        if load_muons:
            self.muon       = self.load_array(self.input_file, 'ana/muon')
        if load_voxels:
            self.voxels     = self.load_array(self.input_file, 'ana/voxels')

        # construct truth info
        # each index in these arrays correspond to an event
        if self.load_neutrons:
            try:
                self.event_ids          = self.neutron['event_id']
                self.neutron_ids        = self.neutron['neutron_ids']
                self.neutron_capture_x  = self.neutron['neutron_capture_x']
                self.neutron_capture_y  = self.neutron['neutron_capture_y']
                self.neutron_capture_z  = self.neutron['neutron_capture_z']
                self.gamma_ids          = self.neutron['gamma_ids']
                self.gamma_neutron_ids  = self.neutron['gamma_neutron_ids']
                self.gamma_energy       = self.neutron['gamma_energy']
                self.edep_energy        = self.neutron['edep_energy']
                self.edep_parent        = self.neutron['edep_parent']
                self.edep_neutron_ids   = self.neutron['edep_neutron_ids']
                self.edep_gamma_ids     = self.neutron['edep_gamma_ids'] 
                self.neutron_x          = self.neutron['edep_x']
                self.neutron_y          = self.neutron['edep_y']
                self.neutron_z          = self.neutron['edep_z']      
                self.electron_ids           = self.neutron['electron_ids']
                self.electron_neutron_ids   = self.neutron['electron_neutron_ids']
                self.electron_gamma_ids     = self.neutron['electron_gamma_ids']
                self.electron_energy        = self.neutron['electron_energy']
                self.edep_num_electrons     = self.neutron['edep_num_electrons']
            except:
                self.logger.error(f"One or more of the required arrays {required_neutron_arrays} is not present in {self.neutron.keys()}.")
                raise ValueError(f"One or more of the required arrays {required_neutron_arrays} is not present in {self.neutron.keys()}.")
        if self.load_muons:
            try: 
                self.num_muons          = self.muon['primary_muons']
                self.muon_ids           = self.muon['muon_edep_ids']
                self.muon_edep_energy   = self.muon['muon_edep_energy']
                self.muon_edep_num_electrons = self.muon['muon_edep_num_electrons']
                self.muon_edep_x        = self.muon['muon_edep_x']
                self.muon_edep_y        = self.muon['muon_edep_y']
                self.muon_edep_z        = self.muon['muon_edep_z'] 
            except:
                self.logger.error(f"One or more of the required arrays {required_muon_arrays} is not present in {self.muon.keys()}.")
                raise ValueError(f"One or more of the required arrays {required_muon_arrays} is not present in {self.muon.keys()}.")
        if self.load_voxels:
            try:
                self.x_min  = self.voxels['x_min']
                self.x_max  = self.voxels['x_max']
                self.y_min  = self.voxels['y_min']
                self.y_max  = self.voxels['y_max']
                self.z_min  = self.voxels['z_min']
                self.z_max  = self.voxels['z_max']
                self.voxel_size = self.voxels['voxel_size']
                self.num_voxels_x   = self.voxels['num_voxels_x']
                self.num_voxels_y   = self.voxels['num_voxels_y']
                self.num_voxels_z   = self.voxels['num_voxels_z']
                self.x_id   = self.voxels['x_id']
                self.y_id   = self.voxels['y_id']
                self.z_id   = self.voxels['z_id']
                self.values = self.voxels['values']
                self.labels = self.voxels['labels']
            except:
                self.logger.error(f"One or more of the required arrays {required_voxel_arrays} is not present in {self.voxels.keys()}.")
                raise ValueError(f"One or more of the required arrays {required_voxel_arrays} is not present in {self.voxels.keys()}.")
        self.num_events = len(self.event_ids)
        self.logger.info(f"Loaded arrays with {self.num_events} entries.")
        if self.load_neutrons:
            # construct positions for neutrons
            self.neutron_edep_positions = np.array(
                [
                    np.array([[
                        self.neutron_x[jj][ii],
                        self.neutron_y[jj][ii],
                        self.neutron_z[jj][ii]]
                        for ii in range(len(self.neutron_x[jj]))
                    ], dtype=float)
                    for jj in range(len(self.neutron_x))
                ], 
                dtype=object
            )
        if self.load_muons:
            self.muon_edep_positions = np.array(
                [
                    np.array([[
                        self.muon_edep_x[jj][ii],
                        self.muon_edep_y[jj][ii],
                        self.muon_edep_z[jj][ii]]
                        for ii in range(len(self.muon_edep_x[jj]))
                    ], dtype=float)
                    for jj in range(len(self.muon_edep_x))
                ], 
                dtype=object
            )
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

    def load_array(self,
        input_file,
        array_name,
    ):
        self.logger.info(f"Attempting to load array: {array_name} from file: {input_file}.")
        try:
            array = input_file[array_name].arrays(library="np")
            self.logger.info(f"Successfully loaded array: {array_name} from file: {input_file}.")
        except Exception:
            self.logger.error(f"Failed to load array: {array_name} from file: {input_file} with exception: {Exception}.")
            raise Exception
        return array

    def plot_event(self,
        index,
        title:  str='',
        show_active_tpc: bool=True,
        show_cryostat:   bool=True,
        save:   str='',
        show:   bool=True,
    ):
        if index >= self.num_events:
            self.logger.error(f"Tried accessing element {index} of array with size {self.num_events}!")
            raise IndexError(f"Tried accessing element {index} of array with size {self.num_events}!")
        fig = plt.figure(figsize=(8,6))
        axs = fig.add_subplot(projection='3d')
        if self.load_neutrons:
            axs.scatter3D(
                self.neutron_x[index], 
                self.neutron_z[index], 
                self.neutron_y[index], 
                label='neutrons', 
                #s=1000*self.edep_energy[index]
            )
        if self.load_muons:
            axs.scatter3D(
                self.muon_edep_x[index],
                self.muon_edep_z[index], 
                self.muon_edep_y[index], 
                label='cosmics', 
                #s=1000*self.muon_edep_energy[index]
            )
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

    def generate_unet_training(self,
        output_file:    str
    ):
        self.logger.info(f"Attempting to generate voxel dataset {output_file}.")
        voxel_coords = np.array([
            [
                [self.x_id[j][i],
                 self.y_id[j][i],
                 self.z_id[j][i]]
                for i in range(len(self.x_id[j]))
            ]
            for j in range(len(self.x_id))
        ])
        feats = [[[1.] for i in range(len(self.values[i]))] for i in range(len(self.values))]
        np.savez(output_file,
            coords=voxel_coords,
            feats = feats,
            labels= self.labels,
            energy= self.values
        )
        self.logger.info(f"Saved voxel dataset to {output_file}.")


if __name__ == "__main__":

    dataset = NeutronCosmicDataset(
        input_file="../neutron_data/protodune_cosmic_voxels.root"
    )

    dataset.generate_unet_training(
        output_file="../neutron_data/unet_dataset.npz",
    )

    dataset.plot_event(
        index=0,
        title='ProtoDUNE cosmic example',
        save='protondune_cosmic_g4'
    )