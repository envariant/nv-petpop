import type { components } from './schema';

type S = components['schemas'];
export type PetSpec = S['PetSpec'];
export type PetSpecPatch = Record<string, unknown>;
export type Species = S['PetSpec_species'];
export type Breed = S['Breed'];
export type BreedList = S['BreedList'];
export type Session = S['Session'];
export type ParseResponse = S['ParseResponse'];
export type Job = S['Job'];
export type JobCreated = S['JobCreated'];
export type JobStatus = Job['status'];
export type Stage = Job['stage'];
export type Artefact = S['Artefact'];
export type ProgressEvent = S['ProgressEvent'];
export type FulfilResponse = S['FulfilResponse'];
export type ResultPage = S['ResultPage'];
export type StaffQueue = S['StaffQueue'];
export type StaffJob = S['StaffJob'];
export type Health = S['Health'];
export type BespokeAccepted = S['BespokeAccepted'];
export type KioskOps = S['KioskOps'];
export type StaffToken = S['StaffToken'];
export type StaffUser = S['StaffUser'];
export type Role = StaffUser['role'];
// Library mode (BRIEF Section 16): Contract 1 (the release) and Contract 2 (the composition).
export type CompositionBody = S['Composition'];
export type ReleaseManifestBody = S['ReleaseManifest'];
export type LibraryRelease = S['LibraryRelease'];
export type LibraryFamilies = S['LibraryFamilies'];
export type LibraryParts = S['LibraryParts'];
export type LibraryPatterns = S['LibraryPatterns'];
export type CompositionStatus = S['CompositionStatus'];
export type CompositionState = CompositionStatus['status'];
export type ExportAccepted = S['ExportAccepted'];
export type KioskOrder = S['KioskOrder'];
// Studio curation (M8).
export type BatchCreate = S['BatchCreate'];
export type Batch = S['Batch'];
export type BatchList = S['BatchList'];
export type BatchFigurine = S['BatchFigurine'];
export type LibraryCandidate = S['LibraryCandidate'];
export type ReviewDecision = S['ReviewDecision'];
export type LibraryItem = S['LibraryItem'];
export type LibraryItemList = S['LibraryItemList'];
export type LibraryItemPatch = S['LibraryItemPatch'];
export type ItemKind = LibraryItem['kind'];
export type ItemStatus = LibraryItem['status'];
export type ReleaseInfo = S['ReleaseInfo'];
export type ReleaseList = S['ReleaseList'];
// Manual mode (decision 111, API 3.2.0): provider requests the operator runs in the vendor's app.
export type ManualTask = S['ManualTask'];
export type ManualTaskList = S['ManualTaskList'];
export type ManualInput = S['ManualInput'];
export type ManualCapability = ManualTask['capability'];
// Per-job GenAI profiles (decision 113, API 3.3.0).
export type GenaiProfiles = S['GenaiProfiles'];
export type GenaiProfileInfo = S['GenaiProfileInfo'];
