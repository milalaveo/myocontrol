import { ChartEvaluation, Chemistry, MachineLearningModel } from '@carbon/icons-react'
import type { Collection } from '../types/cloud'

export const collections = {
  runs: {
    name: 'Experiments',
    path: '/experiments',
    icon: Chemistry,
    description: 'Track experiments executed on your local workstation.',
    title: 'Experiment history',
    tableDescription: 'Configuration, execution status and reproducibility details.',
    empty:
      'Your registered experiments will appear here. Signals uploaded from Electron are listed under Recordings.',
  },
  models: {
    name: 'Models',
    path: '/models',
    icon: MachineLearningModel,
    description: 'Browse published models and their reproducibility metadata.',
    title: 'Published models',
    tableDescription: 'Verified model versions available to your account.',
    empty: 'Published model versions will appear here after a run completes.',
  },
  results: {
    name: 'Results',
    path: '/results',
    icon: ChartEvaluation,
    description: 'Review completed evaluations and compare recognition metrics.',
    title: 'Evaluation results',
    tableDescription: 'Metrics linked to models and frozen research manifests.',
    empty: 'Completed evaluations will appear here with their metrics.',
  },
} satisfies Record<Collection, object>

export const collectionKeys: Collection[] = ['runs', 'models', 'results']
