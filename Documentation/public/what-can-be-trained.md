# What can I train on DIN?

DIN is designed to let a group of people train a shared AI model while keeping their training data on their own devices. Clients train locally, auditors check the results, and aggregators combine the accepted updates into a new shared model.

> **Which version does this describe?** This page covers DevNet 2.0 as represented by the code on the `develop` branch. The [Model_0 getting-started guide](getting-started.md) describes the current public example on Optimism Sepolia, which may differ from DevNet 2.0.

## The short answer

**Many kinds of models can fit DIN, but bringing a new one takes some setup.** DIN does not require a particular model architecture or framework. The model owner supplies the code that tells participants how to train, check, and combine updates. The size of the model is mainly limited by the devices and network connections of the people running it.

The **MNIST handwritten-digit model** is the end-to-end example tested in this repository. If you want to train a different model or use a different dataset, you will need to adapt and test that example's workflow. DIN does not yet offer a one-click way to upload any model and start training it.

| Your idea | Where to start |
|---|---|
| Train a model on similar data held by different people, such as images or rows with the same fields | This is closest to the tested MNIST example. You will need your own model, data preparation, and evaluation code. |
| Train a tabular, language, or other model | Potentially possible with custom code. Test the full training and evaluation workflow before inviting participants. |
| Fine-tune a large language model | A possible approach is to share small adapter updates rather than the full model. This has **not** been tested end to end on DIN; participants would still need access to the base model and suitable hardware. |
| Train when participants can submit at any time | DIN currently works in rounds with scheduled stages, so a fully asynchronous project would need further development. |

The same principle applies to frameworks and training methods: the reference uses PyTorch, while TensorFlow, scikit-learn, JAX, and other Python tools may be usable through custom services. Methods for personalized training, different device sizes, or participants holding different features are possibilities to design and test, not ready-made options.

## What would I need to bring?

You, as the **model owner**, would prepare:

1. **A model and a clear task.** Define what participants are trying to predict or learn, how their data should be prepared, and what a useful result looks like.
2. **Local training code.** Participants called *clients* run this code with their own training data. For the tested example, raw client training data stays on their devices; you should check that your own code behaves the same way.
3. **A separate test dataset and a way to score results.** Participants called *auditors* use test data provided by the model owner to check submitted models. The score should make sense for your task: an image-classification score may not make sense for a regression or language model.
4. **Code to combine updates.** Participants called *aggregators* turn accepted local results into the next shared model.
5. **People and resources to run the task.** You need available clients, auditors, and aggregators, plus enough computing power and storage for the model. Model files are transferred through IPFS, so larger files also mean more upload, download, and storage work.

DIN calls the model-specific Python files **services**. It also uses a **manifest** to tell participants where to find those files, their dependencies, and other task information. The [services guide](services.md) and [manifest guide](manifest.md) explain the details when you are ready to build.

## How does a training round work?

1. The model owner publishes a starting model and opens a training round.
2. Clients train on their local data and submit model updates.
3. Auditors test the submissions using evaluation data from the model owner.
4. Aggregators combine accepted updates into a new shared model.
5. The model owner checks the new model and can start another round.

The model owner moves the task through these stages, so participants need to be available at the right times. The exact training, scoring, and combining rules come from the model's services. See the [model workflow](workflows/model-workflow.md) for the full sequence.

## What should I check before starting?

- **Fit:** Can your project use rounds of local training, checking, and combining results? Start with the [MNIST example](guides/client-onboarding.md) to see the tested path. Its image format and settings are specific to that example.
- **Resources:** Can the participants' devices train, evaluate, or combine your model? The system requirements in [Getting Started](getting-started.md) apply only to Model_0. Measure the needs of your own model.
- **Data and privacy:** Clients can keep raw training data locally, but submitted model updates and other task files are shared. Check what your services send and who can access the evaluation data. Optional [differential privacy settings](../technical/services/clients.md#manifest-driven-dp-configuration) exist in the reference client service, but are off by default and need careful review before making privacy promises.
- **People:** Arrange enough clients, auditors, and aggregators to participate. DIN can show registered models, but the model owner still needs to help people discover the task and join it.
- **Costs:** Allow for transaction fees, model-registration fees, IPFS storage and transfers, participant hardware, and staking by validators. Registration fees differ for open-source and proprietary models and can change; see the [model-owner guide](roles/model-owner.md) before budgeting.

## How do I try it?

If you are new to DIN, follow [Getting Started](getting-started.md) to try the MNIST example first. To bring your own model, use the [model-owner guide](roles/model-owner.md) and [services guide](services.md) to prepare and test your task. A new model must be reviewed before it appears in the registry; later changes to its manifest also require approval. Participants should review the code they are asked to run.

If you are exploring a project with the team, share the model type, the kind and size of data held by each participant, how you would measure success, your expected number of participants, and any hardware or privacy constraints. Those details make it possible to assess the work needed for a first training round. For a broader introduction to collaborating with DIN, see [Explore DIN with your community](partner-introduction.md).
