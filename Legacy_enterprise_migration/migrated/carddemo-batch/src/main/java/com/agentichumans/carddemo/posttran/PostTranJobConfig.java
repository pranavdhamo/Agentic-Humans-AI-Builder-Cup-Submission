package com.agentichumans.carddemo.posttran;

import com.agentichumans.carddemo.cobol.FixedRecordReader;
import com.agentichumans.carddemo.cobol.Records;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.function.Supplier;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * Job "posttran" = CBTRN02C. Step 1 posts (read -> validate/post -> collect); step 2 writes the files the
 * COBOL program leaves behind, in the same record layouts, so they can be compared byte-for-byte.
 */
@Configuration
@ConditionalOnProperty(name = "carddemo.job", havingValue = "posttran", matchIfMissing = true)
class PostTranJobConfig {

    @Bean RunState runState() { return new RunState(); }

    @Bean Supplier<LocalDateTime> clock() { return LocalDateTime::now; }

    @Bean Ledger ledger(@Value("${carddemo.input-dir}") Path inputDir) throws IOException { return Ledger.load(inputDir); }

    @Bean FixedRecordReader dailyTranReader(@Value("${carddemo.dailytran}") Path file) { return new FixedRecordReader(file, Records.DALYTRAN_LEN); }

    @Bean PostTranProcessor postTranProcessor(Ledger ledger, RunState state, Supplier<LocalDateTime> clock) {
        return new PostTranProcessor(ledger, state, clock);
    }

    @Bean ItemWriter<PostTranProcessor.Outcome> outcomeWriter(RunState state) {
        return chunk -> {
            for (PostTranProcessor.Outcome o : chunk) {
                if (o instanceof PostTranProcessor.Posted p) state.posted.add(p);
                else if (o instanceof PostTranProcessor.Rejected r) state.rejects.add(r.rejectRecord());
            }
        };
    }

    @Bean Step postStep(JobRepository repo, PlatformTransactionManager tx, FixedRecordReader reader,
                        PostTranProcessor processor, ItemWriter<PostTranProcessor.Outcome> writer) {
        return new StepBuilder("postTransactions", repo)
                .<String, PostTranProcessor.Outcome>chunk(10, tx)
                .reader(reader).processor(processor).writer(writer).build();
    }

    @Bean Tasklet writeOutputs(RunState state, Ledger ledger, @Value("${carddemo.output-dir}") Path outDir) {
        return (contribution, ctx) -> {
            Files.createDirectories(outDir);
            write(outDir.resolve("DALYREJS.ps"), String.join("", state.rejects));
            StringBuilder trans = new StringBuilder();
            state.posted.stream().sorted(Comparator.comparing(PostTranProcessor.Posted::id))   // indexed file: key order
                    .forEach(p -> trans.append(p.tranRecord()));
            write(outDir.resolve("TRANSACT.flat"), trans.toString());
            StringBuilder accts = new StringBuilder();
            ledger.accounts.values().forEach(a -> accts.append(a.raw()));
            write(outDir.resolve("ACCTDATA.flat"), accts.toString());
            StringBuilder tcats = new StringBuilder();
            ledger.tcat.values().forEach(t -> tcats.append(t.raw()));
            write(outDir.resolve("TCATBALF.flat"), tcats.toString());
            write(outDir.resolve("stdout.txt"), String.format(
                    "START OF EXECUTION OF PROGRAM CBTRN02C%nTRANSACTIONS PROCESSED :%09d%nTRANSACTIONS REJECTED  :%09d%n"
                    + "END OF EXECUTION OF PROGRAM CBTRN02C%n", state.processed, state.rejected));
            write(outDir.resolve("rc.txt"), state.returnCode() + "\n");
            return RepeatStatus.FINISHED;
        };
    }

    private static void write(Path p, String s) throws IOException {
        Files.write(p, s.getBytes(StandardCharsets.ISO_8859_1));
    }

    @Bean Step outputStep(JobRepository repo, PlatformTransactionManager tx, Tasklet writeOutputs) {
        return new StepBuilder("writeOutputs", repo).tasklet(writeOutputs, tx).build();
    }

    @Bean Job postTranJob(JobRepository repo, Step postStep, Step outputStep) {
        return new JobBuilder("posttran", repo).start(postStep).next(outputStep).build();
    }
}
